// Z950 - an MPC insert effect plugin by Keebz
//
// A live S-series style time stretch / pitch shift (Akai S1000 rack sampler, the 90s jungle sound),
// plus a CD-deck style Cue / Jog scrub and a tempo-matched Punch In / Punch Out looper.
//
// How the S1000 stretches (read from the v4.4 firmware, then written from scratch here):
//   Stretching by a factor s (> 1) means inserting one whole cycle of length L (a copy of the audio just played) every
//        D = L * s / (s - 1)
//   output samples, so the output grows by L for every D - L samples of new material. At each insertion the read
//   position jumps back by L and the two read positions are crossfaded over
//        X = min((WIDTH + 1) * L, D)
//   samples. In CYCLIC mode L is the fixed "Cyclic" cycle length. In INTELL mode L is searched: for lags 40..2000 samples
//   (at 44.1 kHz; the S1000 doubles its 20..1000 range for 44.1 kHz samples, and doubles the point count too) the audio is
//   compared with itself shifted by that lag (sum of absolute differences over 2 * (QUAL+1) evenly spaced points of a window of
//   lag * min(D/L, WIDTH+1) samples; a coarse pass at lags 44, 52, ... with step 8, then a step-2 refinement of the four lags
//   below each promising coarse lag), and the best lag, usually the local pitch period, becomes the cycle that is inserted.
//   Checked against the S1000 v4.4 ROM: the search, the window, D, X and the linear crossfade follow it. Two deliberate
//   differences, both for live use: the comparison window is capped at 2048 samples (the ROM allows 16384, which would mean a
//   0.4 s delay) and the lag is searched about every 8 ms instead of at every splice. A third one is an addition: see kLagFloor.
//
//   Power   on / off      off = the plugin is out of the circuit: the input passes straight to the output (no delay, no effect),
//                         a loop is dropped. On again starts clean from live.
//   Mode    CYCLIC / INTELL
//   Cyclic  0..2000 smp   CYCLIC: the cycle length L (S2800 manual). 0 = Auto: L is searched like INTELL does.
//                         In INTELL the same knob is the STYLE: left = ORIG (the S1000's lag search exactly as the ROM has it), right = CLEAN
//                         (default: a search that ends on the shortest lags is repeated for lags of 5 ms and more; no 1 ms comb on drums).
//   Qual    0..100        INTELL: number of comparison points (QUAL + 1) of the lag search. Default 90.
//   Width   0..100        INTELL: crossfade length is (WIDTH + 1) cycles, up to the whole spacing D. Default 90.
//   Length  100..2000 %   100 = off (dry, no latency). Above 100 the live input is stretched without pitch change: the
//                         output falls further behind the input the longer you hold it, and returning to 100 snaps back
//                         to the live signal. With Pitch on the same knob spans 100..300 % (finer steps).
//   Speed   -100..+100 %    turntable-style speed of the audio stored in the looper (a running loop) and of the Cue stutter; it
//                         catches at 0 (inside +-2 it snaps to exactly 0) and is greyed out while neither is active. It reacts at once:
//                         the loop is read by a small overlap-add player (about 30 ms grains). Pitch off: the pitch stays; Pitch on:
//                         the pitch follows. In Cue the stutter repeats faster or slower with the speed.
//   Pitch   off/on        on: stretch, then resample by the same factor: duration stays, pitch rises by Length/100.
//   Filter  0..99         the Akai S900/S950 low-pass at the very end of the chain, 1:1: a 6th-order Butterworth (National MF6-50, -36 dB/oct, no
//                         resonance) with the S950 ROM's cutoff law (integer clock dividers): up to about 22 it sits at ~314 Hz, 22..80
//                         sweeps six octaves up to ~20 kHz, above 80 it is open (out of the circuit).
//                         Both values are remembered: the key only changes which one the knob edits.
//   Bit     8/12/16/24    bit depth of the output (24, all the way right, = untouched)
//   Rate    8000..44100   true sample-rate reduction (zero-order hold) of the output (44100 = off)
//   Cue     off/on        stutter on/off: repeats the last 1/8 s, like a CD deck cue. Released inside a loop it moves the loop's
//                         START to where the stutter began (the loop rotates inside its own audio).
//   Jog     0..800        scrub wheel, one step = one CD frame (13.3 ms), relative to where Cue was pressed. The MPC sends no MIDI to
//                         effect plugins, so the touch strip drives it through the host's own assignment (Crossfader mode).
//   Punch In / Punch Out  press to set the loop start / end; the keys light while the loop is set / defined
//   Loop Run (stop/start) stops the loop WITHOUT dumping it (live audio comes back) and starts it again from its start;
//                         a stopped loop is remembered while its audio is still in the ring (about 40 s)
//   Loop    Free,1/1..1/64 loop length in note values at the host tempo (Free = the tapped length). Changing it cuts the
//                         loop to that fraction measured from the loop's start and restarts playback there.
//
// Signal flow
//   input -> ring buffer (always recording, ~47 s at 44.1 kHz)
//         -> splice engine (see above) inside the loop when looping, at the live edge otherwise
//         -> Cue slice (1/8 s repeated) -> sample-rate hold -> bit depth -> low-pass filter -> output
//
// Everything runs on the audio thread without allocation; buffers are created in prepare().
// A small helper thread tells the host when the plugin itself changed a parameter (lit Punch keys, Length text),
// so the screen follows.

#include "mpc_plugin.h"
#include "dsp/tempo.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <string>
#include <thread>
#include <vector>

namespace {

enum ParamIndex
{
    kCyclic = 0,   // smp   (parameter 0: the host nudges it on load; harmless, it only changes the cycle length)
    kLength,       // %
    kPhaseLegacy,  // spare: this slot was Phase in the first builds. Kept (unused) so that an old project or preset cannot leak a value into the Filter
    kBits,         // 8 / 12 / 16 / 24 (knob left .. right)
    kRate,         // Hz
    kPitch,        // off / on
    kQual,         // 0..100
    kWidth,        // 0..100
    kMode,         // CYCLIC / INTELL
    kCue,          // off / on
    kJog,          // 0..800 CD frames, centre 400
    kPunchIn,      // press / lit
    kPunchOut,     // press / lit
    kLoopLen,      // Free, 1/1 .. 1/64
    kLoopBpm,      // display only: the tempo of the running loop
    kLoopRun,      // stop / start the loop (lit while it runs)
    kFilterSel,    // spare (was the Cut/Res key: the S950 filter has no resonance, so it is gone); kept so the parameter order never changes
    kCutVal,       // spare
    kResVal,       // spare
    kSpeed,        // -100..+100 %
    kPower,        // on / off (off = bypass)
    kSpeedLive,    // display only: lit while Speed has something to act on (a running loop or Cue)
    kFilter,       // 0..99: the S950 filter value (appended: a new slot)
    kCycStore,     // stored Cyclic value (hidden: the knob's value while the mode is CYCLIC)
    kStyleStore,   // stored INTELL style (hidden): < 1000 = Original (the S1000's search as it is), >= 1000 = Clean
    kNumParams
};

constexpr int   kFadeSamples = 32;                         // de-click ramp on each cue slice
constexpr float kLenBeats[] = { 0.0f, 4.0f, 2.0f, 1.0f, 0.5f, 0.25f, 0.125f, 0.0625f };   // Free, 1/1 .. 1/64
constexpr int   kNumLens    = (int)(sizeof(kLenBeats) / sizeof(kLenBeats[0]));
constexpr int   kBitDepths[] = { 8, 12, 16, 24 };         // knob left .. right; 24 (all the way right) is untouched
constexpr int   kJogCentre  = 400;
constexpr float kSpeedCatch = 3.0f;                        // Speed snaps to 0 inside +-3 %
constexpr double kPitchLenMax = 300.0;                     // with Pitch on, the Length knob spans 100..300 %
constexpr double kLagFloor  = 220.0;                       // 5 ms at 44.1 kHz: see searchLag
constexpr int   kMaxCoarse  = 640;                         // lag search: coarse candidates (step 8) at any sample rate

// effective stretch length in percent: with Pitch on the knob's whole travel (100..2000) maps to 100..300
inline double effectiveLength(int plain, bool pitchOn)
{
    return pitchOn ? 100.0 + (double)(plain - 100) * (kPitchLenMax - 100.0) / 1900.0 : (double)plain;
}

} // namespace

class DeepStretch : public mpc::Plugin
{
public:
    DeepStretch() : mpc::Plugin(makeInfo())
    {
        addParam(mpc::intParam  ("cyclic", "Cyclic", 0, 2000, 2000, "smp"));
        addParam(mpc::intParam  ("length", "Length", 100, 2000, 100, "%"));
        {
            mpc::Param ph = mpc::floatParam("phase", "Phase", 0.0f, 100.0f, 0.0f, "", 1);   // spare slot, no function
            ph.automatable = false;
            addParam(ph);
        }
        addParam(mpc::choiceParam("bits",  "Bit",    {"8", "12", "16", "24"}, 3));
        addParam(mpc::intParam  ("rate",   "Rate",   8000, 44100, 44100, "Hz"));
        addParam(mpc::boolParam ("pitch",  "Pitch",  false));
        addParam(mpc::intParam  ("qual",   "Qual",   0, 100, 90, ""));
        addParam(mpc::intParam  ("width",  "Width",  0, 100, 90, ""));
        addParam(mpc::boolParam ("mode",   "Mode",   false));              // false = CYCLIC, true = INTELL
        addParam(mpc::boolParam ("cue",    "Cue",    false));
        addParam(mpc::intParam  ("jog",    "Jog",    0, 800, kJogCentre, "fr"));
        addParam(mpc::boolParam ("punchIn",  "Punch In",  false));
        addParam(mpc::boolParam ("punchOut", "Punch Out", false));
        addParam(mpc::choiceParam("loopLen", "Loop", {"Free", "1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"}, 0));
        {
            mpc::Param bp = mpc::floatParam("loopBpm", "Loop BPM", 0.0f, 999.0f, 0.0f, "", 1);   // shown above the Punch keys
            bp.automatable = false;
            addParam(bp);
        }
        addParam(mpc::boolParam ("loopRun", "Loop Run", false));
        {
            mpc::Param fs = mpc::boolParam("filterSel", "Spare 1", false);                  // three spare slots (see ParamIndex): no function
            mpc::Param c  = mpc::floatParam("cutVal", "Spare 2", 0.0f, 100.0f, 100.0f, "", 1);
            mpc::Param r  = mpc::floatParam("resVal", "Spare 3", 0.0f, 100.0f, 0.0f, "", 1);
            fs.automatable = c.automatable = r.automatable = false;
            addParam(fs);
            addParam(c);
            addParam(r);
        }
        addParam(mpc::floatParam("speed", "Speed", -100.0f, 100.0f, 0.0f, "%", 1));
        addParam(mpc::boolParam ("power", "Power", true));
        {
            mpc::Param sl = mpc::boolParam("speedLive", "Speed On", false);
            sl.automatable = false;
            addParam(sl);
        }
        addParam(mpc::intParam("filter", "Filter", 0, 99, 99, ""));                 // the S950 scale: 99 = open
        {
            // The first knob (parameter 0) is the Cyclic length in CYCLIC mode and the INTELL style in INTELL mode; each mode keeps its own value.
            mpc::Param cs = mpc::intParam("cycStore", "Cyclic Store", 0, 2000, 2000, "smp");
            mpc::Param ss = mpc::intParam("styleStore", "Style Store", 0, 2000, 2000, "");
            cs.automatable = ss.automatable = false;
            addParam(cs);
            addParam(ss);
        }

        // Built-in programs. `P` lists every parameter in order, so no program can leave one at a stale value.
        auto P = [](float cyc, float len, float bits, float rate, float pitch, float mode, float loopLen, float cut, float res) -> std::vector<float>
        {
            //          cyclic length (spare) bits rate  pitch qual width mode cue jog  punchIn punchOut loop bpm run sel cut res speed power live filter
            return {mode > 0.5f ? 2000.0f : cyc, len, 0.0f, bits, rate, pitch, 90, 90, mode, 0, 400, 0, 0, loopLen, 0, 0, 0, cut, res, 0, 1, 0, cut, cyc, 2000.0f};
        };
        addProgram("Default",         P(2000, 100, 3, 44100, 0, 0, 0, 99, 0));
        addProgram("Punch 300%",      P(2000, 300, 3, 44100, 0, 0, 0, 99, 0));
        addProgram("Intell 200%",     P(2000, 200, 3, 44100, 0, 1, 0, 99, 0));
        addProgram("Jungle Stretch",  P(1200, 450, 1, 32000, 0, 0, 0, 99, 0));
        addProgram("Chipmunk +1oct",  P(1500, 1050, 3, 44100, 1, 0, 0, 99, 0));        // 1050 = 200 % with Pitch on
        addProgram("Dark Tape",       P(2000, 250, 3, 44100, 0, 0, 0, 33, 0));
        addProgram("S950 12-bit",     P(2000, 150, 1, 36000, 0, 0, 0, 99, 0));
        addProgram("Lo-Fi 8-bit",     P(2000, 200, 0, 12000, 0, 0, 0, 99, 0));
        addProgram("Beat Repeat 1/8", P(600, 100, 3, 44100, 0, 0, 4, 99, 0));

        notifier_ = std::thread([this] { notifierLoop(); });
    }

    ~DeepStretch() override
    {
        stopNotifier_.store(true);
        if (notifier_.joinable()) notifier_.join();
    }

    void prepare(double sampleRate, int maxBlockSize) override
    {
        (void)maxBlockSize;
        // Only a new sample rate (or the first call) reallocates the buffers and throws a loop away: a host that suspends / resumes the
        // plugin or changes the block size must not wipe a running loop or the audio it was recorded from.
        const bool realloc = ring_[0].empty() || sampleRate != sampleRate_;
        sampleRate_ = sampleRate;
        vsLoop_.setup(sampleRate);
        vsCue_.setup(sampleRate);
        if (realloc)
        {
            int64_t want = (int64_t)(sampleRate * 24.0);
            int64_t n = 1 << 16;
            while (n < want) n <<= 1;
            ringSize_ = n;
            mask_ = n - 1;
            ring_[0].assign((size_t)n, 0.0f);
            ring_[1].assign((size_t)n, 0.0f);
            mono_.assign((size_t)n, 0.0f);
            guard_ = (int64_t)(0.3 * sampleRate) + 1024;
            writeAbs_ = 0;
            looping_ = armed_ = haveA_ = frozen_ = false;
            loopFree_ = false; loopDefined_ = false; fullLen_ = rot_ = 0;
            bpmValid_.store(false);
            anaPos_ = hB_ = -1000.0;
        }
        reset();
    }

    // reset() clears only transient state (effect tails, crossfades, cue): the ring buffer and a loop survive it.
    void reset() override
    {
        stretchGain_ = 0.0f;
        vsLoop_.running = vsCue_.running = false; vsMix_ = 0.0f;
        held_[0] = held_[1] = 0.0f;
        rateAcc_ = 0.0;
        for (int c = 0; c < 2; ++c) for (int k = 0; k < 6; ++k) ladder_[c][k] = 0.0f;
        lastModeSw_ = getBool(kMode);
        lastCyc_ = get(kCyclic);
        gSmooth_ = -1.0f;
        xfPos_ = xfLen_ = 0;
        evCount_ = 1.0;
        lagCache_ = 0;
        sinceSearch_ = 1 << 30;
        cueActive_ = cueOn_ = false;
        pauseMix_ = 0.0f;
        slicePhase_ = 0;
        shownIn_ = shownOut_ = shownRun_ = false;
        lenBeats_ = kLenBeats[mpc::clamp(getInt(kLoopLen), 0, kNumLens - 1)];
        lastLoopLen_ = getInt(kLoopLen);
        lastIn_ = getBool(kPunchIn);
        lastOut_ = getBool(kPunchOut);
        lastRun_ = getBool(kLoopRun);
        if (!looping_) anaPos_ = hB_ = (double)writeAbs_ - 1000.0;
    }

    // Length shows the effective value (100..300 while Pitch is on)
    bool formatValue(int index, float plainValue, std::string& out) override
    {
        if (index == kLength)
        {
            out = std::to_string((int)std::lround(effectiveLength((int)std::lround(plainValue), getBool(kPitch))));
            return true;
        }
        if (index == kCyclic && getBool(kMode))                  // INTELL: the first knob chooses the style
        {
            out = plainValue >= 1000.0f ? "CLEAN" : "ORIG";
            return true;
        }
        if (index == kSpeed)
        {
            char buf[16];
            std::snprintf(buf, sizeof(buf), "%+.1f", (double)plainValue);
            out = buf;
            return true;
        }
        if (index == kLoopBpm)
        {
            char buf[32];
            if (bpmValid_.load() && plainValue >= 1.0f) std::snprintf(buf, sizeof(buf), "%.1f BPM", (double)plainValue);
            else std::snprintf(buf, sizeof(buf), "---");
            out = buf;
            return true;
        }
        return false;
    }

    void parameterChanged(int index, float plainValue) override
    {
        (void)plainValue;
        if (index == kPitch) markDirty(kLength);       // the Length text changes meaning with Pitch
    }

    void process(mpc::ProcessContext& ctx) override
    {
        if (ring_[0].empty() || ctx.numOutputs < 1) return;

        const int    n   = ctx.numFrames;
        const int    nch = mpc::clamp(ctx.numOutputs, 1, 2);
        const double sr  = ctx.sampleRate;

        // ---- Power: off = plain bypass. The loop and the effects are dropped so that turning it on again starts clean from live ----
        if (!getBool(kPower))
        {
            if (poweredOn_)
            {
                poweredOn_ = false;
                looping_ = armed_ = haveA_ = loopDefined_ = loopFree_ = frozen_ = false;
                cueOn_ = cueActive_ = false;
                fullLen_ = rot_ = 0;
                bpmValid_.store(false); markDirty(kLoopBpm);
                stretchGain_ = 0.0f; pauseMix_ = 0.0f;
                for (int c = 0; c < 2; ++c) for (int k = 0; k < 6; ++k) ladder_[c][k] = 0.0f;
                gSmooth_ = -1.0f;
                xfPos_ = xfLen_ = 0; evCount_ = 1.0; lagCache_ = 0; sinceSearch_ = 1 << 30;
            }
            if (ctx.inputs != nullptr)
                for (int c = 0; c < nch; ++c)
                {
                    const float* in = ctx.inputs[(c < ctx.numInputs) ? c : 0];
                    if (in != nullptr && in != ctx.outputs[c])
                        for (int i = 0; i < n; ++i) ctx.outputs[c][i] = in[i];
                }
            syncState(kPunchIn, false, shownIn_, lastIn_);
            syncState(kPunchOut, false, shownOut_, lastOut_);
            syncState(kLoopRun, false, shownRun_, lastRun_);
            syncState(kSpeedLive, false, shownLive_, lastLive_);
            vsLoop_.running = vsCue_.running = false; vsMix_ = 0.0f;
            anaPos_ = hB_ = (double)writeAbs_ - 1000.0;
            return;
        }
        if (!poweredOn_)                                      // switched on again: start clean from live
        {
            poweredOn_ = true;
            lastIn_ = getBool(kPunchIn); lastOut_ = getBool(kPunchOut); lastRun_ = getBool(kLoopRun);
        }
        const double ks  = sr / 44100.0;                                  // the firmware's sample counts are at 44.1 kHz
        const mpc::Transport& tr = ctx.transport;

        // ---- stretch parameters -------------------------------------------------------------------
        const int    lengthPlain = getInt(kLength);
        // Speed catches at 0 like a centre detent: inside +-2 the knob is pulled to exactly 0, so it is easy to reset
        if (get(kSpeed) != 0.0f && std::fabs(get(kSpeed)) < kSpeedCatch)
        {
            set(kSpeed, 0.0f);
            markDirty(kSpeed);
        }
        const double rate      = std::max(0.0, 1.0 + (double)get(kSpeed) * 0.01);           // turntable speed 0 .. 2 (loop and cue only)
        const bool   pitchOn   = getBool(kPitch);
        const double lenRatio  = std::max(1.0, effectiveLength(lengthPlain, pitchOn) * 0.01);
        // The splice engine (Length) runs at normal speed: sRatio is its time-stretch factor, q the stretched samples read per output sample.
        const double sRatio    = lenRatio;
        const double q         = pitchOn ? lenRatio : 1.0;
        const bool   spliceOn  = sRatio > 1.002;
        const double dPerL     = sRatio / std::max(1e-6, sRatio - 1.0);    // D / L
        // The Speed player (loop and cue only): net playback rate vsR, grain read speed vsF (the pitch factor)
        const bool   speedWanted = std::fabs(rate - 1.0) > 0.002;
        const double vsR       = pitchOn ? rate : rate / lenRatio;
        const double vsF       = pitchOn ? lenRatio * rate : 1.0;                // (0 = the record stands still)
        const double cueR      = std::max(0.05, rate);                     // the stutter ignores Length (at -100 it crawls at 1/20)
        const double cueF      = pitchOn ? cueR : 1.0;
        const bool   intell    = getBool(kMode);
        const int    cyclicSmp = getInt(kCycStore);
        const bool   clean     = get(kStyleStore) >= 1000.0f;            // INTELL style: Clean (default) or Original
        const bool   useSearch = intell || cyclicSmp <= 0;                // INTELL, or CYCLIC with Auto (Cyclic = 0)
        const int    cycleFixed = mpc::clamp((int)std::lround((double)cyclicSmp * ks), 8, (int)std::lround(2000.0 * ks));
        const int    nPts      = intell ? (getInt(kQual) + 1) * 2 : 48;   // the S1000 doubles the point count for 44.1 kHz samples
        const int    widthMul  = (intell ? getInt(kWidth) : 10) + 1;       // CYCLIC: a fixed 11 cycles, like the S2800 screen default
        const int    lMin      = (int)std::lround(40.0 * ks);             // S1000 at 44.1 kHz: Lmin 40, Lmax 2000
        const int    lMax      = (int)std::lround(2000.0 * ks);
        const int    wCap      = (int)std::lround(2048.0 * ks);           // longest comparison window (the ROM: 16384; this bounds the latency)
        const int    lFloor    = (int)std::lround(kLagFloor * ks);
        const int    aheadMargin = (useSearch ? wCap : 0) + 64;           // the search looks this far ahead of the read head
        const double lag0      = (double)(aheadMargin + 64);              // distance behind the live input when the stretch starts
        const double lagCap    = (double)(ringSize_ - guard_ - 4);
        const int    searchEvery = (int)std::lround(350.0 * ks);

        const int    rateHz    = getInt(kRate);
        const double rateStep  = mpc::clamp((double)rateHz / sr, 0.05, 1.0);                // < 1: hold samples
        const bool   rateOn    = rateHz < 44000 && rateStep < 0.9999;
        const int    bitsIdx   = mpc::clamp(getInt(kBits), 0, 3);
        const bool   bitsOn    = bitsIdx < 3;
        const float  bitLevels = (float)(1 << (kBitDepths[bitsIdx] - 1));

        // ---- the first knob: Cyclic length (CYCLIC) or INTELL style (INTELL); each mode keeps its own value ----
        {
            const bool m = getBool(kMode);
            if (m != lastModeSw_)
            {
                lastModeSw_ = m;
                set(kCyclic, get(m ? kStyleStore : kCycStore));
                markDirty(kCyclic);
                lastCyc_ = get(kCyclic);
            }
            else
            {
                const float v = get(kCyclic);
                if (v != lastCyc_) { lastCyc_ = v; set(m ? kStyleStore : kCycStore, v); }
            }
        }
        // The Akai S900/S950 low-pass: a National MF6-50 6th-order Butterworth (-36 dB/oct, no resonance), its cutoff set by a clock divider from
        // the Filter value. Open (no filtering) once the cutoff reaches the top of the audio band.
        const double fcHz      = s950Cutoff(getInt(kFilter));
        const bool   filterOn  = fcHz < 0.46 * sr;
        const float  fcTarget  = (float)std::min(fcHz, 0.45 * sr);
        const float  gTarget   = std::tan(3.14159265f * fcTarget / (float)sr);
        const float  kSec[3]   = { 1.0f / 0.51764f, 1.0f / 0.70711f, 1.0f / 1.93185f };   // 1/Q of the three Butterworth sections
        if (gSmooth_ < 0.0f) gSmooth_ = gTarget;

        // ---- loop helpers ---------------------------------------------------------------------------
        const int64_t maxLoop = ringSize_ - guard_ - 8;
        const int64_t minLoop = 64;
        const int64_t tapAbs  = writeAbs_;                    // block start: the tap error is one host block
        auto lenSamples = [&](float beats) -> int64_t
        {
            int64_t s = (int64_t)std::llround((double)mpc::dsp::beatsToSamples(beats, tr.bpm, sr));
            return mpc::clamp<int64_t>(s, minLoop, maxLoop);
        };
        auto snapBack = [&](int64_t absPos) -> int64_t      // snap a tap back to the previous grid line; Free = no snap
        {
            if (lenBeats_ <= 0.0f || !tr.playing || !tr.ppqValid) return absPos;
            double phase = std::fmod(tr.ppqPos, (double)lenBeats_);
            if (phase < 0.0) phase += (double)lenBeats_;
            return absPos - (int64_t)std::llround(phase * 60.0 / (double)mpc::dsp::safeBpm(tr.bpm) * sr);
        };
        const double hostBpm = (double)mpc::dsp::safeBpm(tr.bpm);
        auto showBpm = [&](double bpm)                       // the tempo shown above the Punch keys
        {
            bpmValid_.store(true);
            set(kLoopBpm, (float)mpc::clamp(bpm, 1.0, 999.0));
            markDirty(kLoopBpm);
        };
        auto beginPlayback = [&]()                           // (re)start playing the loop from its start
        {
            looping_ = true; armed_ = false;
            anaPos_ = hB_ = (double)A_;
            xfPos_ = xfLen_ = 0;
            evCount_ = 1.0;
            vsJumpPending_ = true; vsJumpPos_ = (double)A_;
        };
        auto defineLoop = [&]()                              // a new loop has just been set (Punch Out / the armed length reached)
        {
            loopDefined_ = true;
            if (get(kSpeed) != 0.0f) { set(kSpeed, 0.0f); markDirty(kSpeed); }       // a new loop always starts at normal speed
            fullLen_ = B_ - A_; rot_ = 0;
            // A loop tapped in Free mode keeps its own length and counts as 1/1 (4 beats): it is not tied to the master tempo.
            loopFree_ = (lenBeats_ <= 0.0f);
            freeLen_ = (double)(B_ - A_);
            shownBpm_ = loopFree_ ? 240.0 * sr / std::max(1.0, freeLen_) : hostBpm;
            showBpm(shownBpm_);
            beginPlayback();
        };
        auto stopLoop = [&]()                                // stop playing but keep the loop: the live audio is back
        {
            looping_ = false; frozen_ = false;
            anaPos_ = hB_ = (double)writeAbs_ - lag0;
            xfPos_ = xfLen_ = 0;
            evCount_ = 1.0;
        };
        auto exitLoop = [&]()                                // dump the loop
        {
            stopLoop();
            armed_ = false; haveA_ = false; loopDefined_ = false; loopFree_ = false;
            fullLen_ = rot_ = 0;
            bpmValid_.store(false); markDirty(kLoopBpm);
        };
        auto restartAtStart = [&]()                          // jump playback back to the loop's start (crossfaded)
        {
            if (xfPos_ < xfLen_) anaPos_ = hB_;
            hB_ = (double)A_;
            xfPos_ = 0; xfLen_ = 256; xfRho_ = 1.0f;
            evCount_ = 1.0;
            vsJumpPending_ = true; vsJumpPos_ = (double)A_;
        };

        // ---- Loop length dial ------------------------------------------------------------------------
        const int lenIdx = mpc::clamp(getInt(kLoopLen), 0, kNumLens - 1);
        if (lenIdx != lastLoopLen_)
        {
            lastLoopLen_ = lenIdx;
            lenBeats_ = kLenBeats[lenIdx];
            if (loopDefined_ && loopFree_)
            {
                // a Free loop counts as 1/1: the dial cuts it to that fraction of its own length (no master tempo involved)
                const double ratio = (lenIdx == 0) ? 1.0 : (double)kLenBeats[lenIdx] / 4.0;
                B_ = A_ + std::max<int64_t>(minLoop, (int64_t)std::llround(freeLen_ * ratio));
            }
            else if (loopDefined_ && lenBeats_ > 0.0f) B_ = std::min<int64_t>(A_ + lenSamples(lenBeats_), writeAbs_ - 2);
            else if (!loopDefined_ && haveA_ && lenBeats_ > 0.0f) { armed_ = true; armB_ = A_ + lenSamples(lenBeats_); }
            if (loopDefined_)
            {
                if (rot_ != 0) B_ = std::min(B_, A_ + fullLen_);      // a rotated loop cannot be longer than its own audio
                if (looping_) restartAtStart();                       // the new ratio always plays from the loop's start
            }
        }

        // ---- Punch In / Punch Out: a change of the switch is one press; the keys then show the real state --------
        bool v = getBool(kPunchIn);
        if (v != lastIn_)
        {
            lastIn_ = v;
            if (loopDefined_) exitLoop();
            A_ = snapBack(tapAbs);
            haveA_ = true;
            if (lenBeats_ > 0.0f) { armed_ = true; armB_ = A_ + lenSamples(lenBeats_); }
            else armed_ = false;
        }
        v = getBool(kPunchOut);
        if (v != lastOut_)
        {
            lastOut_ = v;
            if (loopDefined_) exitLoop();                    // Punch Out again dumps the loop; the Stop/Start key only stops it
            else if (haveA_)
            {
                int64_t b = armed_ ? std::min(armB_, tapAbs) : tapAbs;
                if (b - A_ >= minLoop && b - A_ <= maxLoop && tapAbs - A_ <= maxLoop) { B_ = b; defineLoop(); }
            }
        }
        v = getBool(kLoopRun);
        if (v != lastRun_)                                    // Stop / Start: keeps the loop, brings the live audio back
        {
            lastRun_ = v;
            if (looping_) stopLoop();
            else if (loopDefined_)
            {
                if (!loopFree_ && lenBeats_ > 0.0f) B_ = std::min<int64_t>(A_ + lenSamples(lenBeats_), writeAbs_ - 2);
                if ((writeAbs_ - A_) <= maxLoop && B_ - A_ >= minLoop) beginPlayback();
                else exitLoop();                              // the loop's audio has left the ring: it cannot be restarted
            }
            if (getBool(kLoopRun) != looping_)                // nothing to start: the key falls back to unlit
            {
                setNormalised(kLoopRun, looping_ ? 1.0f : 0.0f);
                markDirty(kLoopRun);
                lastRun_ = looping_;
            }
        }
        // tempo-locked loop length follows tempo changes
        if (looping_ && !loopFree_ && lenBeats_ > 0.0f)
        {
            B_ = std::min<int64_t>(A_ + lenSamples(lenBeats_), writeAbs_ - 2);
            if (rot_ != 0) B_ = std::min(B_, A_ + fullLen_);
            if (std::fabs(hostBpm - shownBpm_) >= 0.1) { shownBpm_ = hostBpm; showBpm(hostBpm); }   // tempo-locked: shows the sequence tempo
        }
        if (armed_) { if (lenBeats_ > 0.0f) armB_ = A_ + lenSamples(lenBeats_); else armed_ = false; }
        if (looping_ && B_ - A_ < minLoop) B_ = A_ + minLoop;

        // stop recording only when the loop start is about to be overwritten
        frozen_ = looping_ && (A_ < writeAbs_ + n - (ringSize_ - guard_));

        // ---- Cue: the key is a plain on/off switch ---------------------------------------------------------
        cueActive_ = getBool(kCue);

        // ---- Cue / Jog ------------------------------------------------------------------------------
        const int  frameLen = std::max(kFadeSamples * 2, (int)std::lround(sr / 75.0));      // one CD frame = jog step
        const int  cueLen   = (int)std::lround(sr * 0.125);                                   // stutter length: 1/8 s
        bool cueJustStarted = false;
        if (cueActive_ && !cueOn_)
        {
            cueOn_ = true;
            cueJustStarted = true;
            cuePos_ = anaPos_ - (double)cueLen;       // repeat the last 1/8 s that has already played
            jogRef_ = getInt(kJog);
            lastTotal_ = 0;
            slicePhase_ = 0;
            sliceLen_ = cueLen;
        }
        else if (!cueActive_ && cueOn_)
        {
            cueOn_ = false;
            if (looping_)
            {
                // in a loop the point where the stutter began becomes the loop's new start: the loop rotates inside its own audio
                if (fullLen_ > 0)
                {
                    const int64_t sh = (int64_t)std::llround(pendS0_ - (double)A_);
                    rot_ = ((rot_ + sh) % fullLen_ + fullLen_) % fullLen_;
                    if (rot_ != 0) B_ = std::min(B_, A_ + fullLen_);
                }
                restartAtStart();
            }
            else
            {
                anaPos_ = hB_ = (double)writeAbs_ - lag0;                                // live: snap back to live
                xfPos_ = xfLen_ = 0;
                evCount_ = 1.0;
            }
        }
        if (cueOn_)
        {
            const int jog = getInt(kJog);
            const int total = jog - jogRef_;                                               // relative to where Cue was pressed
            pendS0_ = cuePos_ + (double)total * (double)frameLen;
            if (looping_)
            {
                const double L = (double)(B_ - A_);
                if (L > 1.0)
                {
                    while (pendS0_ >= (double)B_) pendS0_ -= L;
                    while (pendS0_ < (double)A_)  pendS0_ += L;
                }
            }
            else
            {
                const double hi = (double)writeAbs_ - (double)cueLen - 4.0;
                const double lo = (double)(writeAbs_ - ringSize_ + guard_);
                pendS0_ = mpc::clamp(pendS0_, lo, hi);
            }
            if (cueJustStarted) sliceS0_ = pendS0_;
            if (total != lastTotal_ || sliceLen_ != cueLen)   // scrubbing: jump to the new frame at once, do not wait for the repeat
            {
                lastTotal_ = total;
                sliceS0_ = pendS0_;
                slicePhase_ = 0;
                sliceLen_ = cueLen;
            }
        }

        const bool   engineOn = spliceOn || looping_ || cueOn_;
        if (speedWanted != cueSpeedMode_)                      // the stutter changes player at 0: restart the slice (with its fade) instead of jumping
        {
            cueSpeedMode_ = speedWanted;
            slicePhase_ = 0;
            vsCue_.running = false;
        }
        const int    sliceOut = speedWanted ? std::max(kFadeSamples * 4, (int)std::lround((double)cueLen / cueR)) : cueLen;   // stutter length in output samples
        const float  stretchTarget = engineOn ? 1.0f : 0.0f;
        const float  pauseTarget = cueOn_ ? 1.0f : 0.0f;

        // ---- per-sample processing ---------------------------------------------------------------------
        for (int i = 0; i < n; ++i)
        {
            float x[2];
            for (int c = 0; c < 2; ++c)
            {
                const int ic = (c < ctx.numInputs) ? c : 0;
                x[c] = (ctx.inputs != nullptr && ctx.numInputs > 0 && ctx.inputs[ic] != nullptr) ? ctx.inputs[ic][i] : 0.0f;
            }

            if (!frozen_)
            {
                const size_t w = (size_t)(writeAbs_ & mask_);
                ring_[0][w] = x[0];
                ring_[1][w] = x[1];
                mono_[w] = 0.5f * (x[0] + x[1]);
                ++writeAbs_;
            }
            if (armed_ && writeAbs_ >= armB_) { B_ = armB_; defineLoop(); }

            stretchGain_ += (stretchTarget - stretchGain_) * 0.002f;
            float sig[2] = {x[0], x[1]};

            if (!engineOn && stretchGain_ < 1e-4f && pauseMix_ < 1e-4f)
            {
                // Idle: keep the read head parked behind the write head.
                stretchGain_ = 0.0f;
                anaPos_ = hB_ = (double)writeAbs_ - lag0;
                xfPos_ = xfLen_ = 0;
                evCount_ = 1.0;
            }
            else
            {
                // --- Speed player on a loop: its position becomes the splice engine's, so handing back is seamless ---
                // The player owns a running loop (it plays at speed 1 exactly like the plain read, so going through 0 never switches engines);
                // only a stretched loop at normal speed (Length above 100) is left to the splice engine.
                const bool vsWant = looping_ && !cueOn_ && (!spliceOn || speedWanted);
                vsMix_ += ((vsWant ? 1.0f : 0.0f) - vsMix_) * 0.01f;
                if (vsWant && !vsLoop_.running) { vsLoop_.wrap = false; vsLoop_.start(anaPos_); }
                if (vsJumpPending_) { vsJumpPending_ = false; if (vsLoop_.running) vsLoop_.start(vsJumpPos_); }
                if (!vsWant && vsLoop_.running && vsMix_ < 1e-3f) vsLoop_.running = false;
                const bool vsOnly = vsLoop_.running && vsMix_ > 0.999f;
                if (vsOnly) { anaPos_ = hB_ = vsLoop_.cur; xfPos_ = xfLen_ = 0; evCount_ = 1.0; }

                // --- read heads: both streams advance q per output sample; a looped, unstretched signal plays at speed 1 ---
                if (!cueOn_ && !vsOnly)
                {
                    const double adv = spliceOn ? q : 1.0;
                    anaPos_ += adv; hB_ += adv;
                    if (looping_) { anaPos_ = wrapLoop(anaPos_); hB_ = wrapLoop(hB_); }
                    else if (spliceOn)
                    {
                        const double lag = (double)writeAbs_ - anaPos_;
                        if (lag < (double)aheadMargin || lag > lagCap)         // too close to the input / out of buffer: re-sync to live
                        {
                            if (xfPos_ < xfLen_) anaPos_ = hB_;
                            hB_ = (double)writeAbs_ - lag0;
                            xfPos_ = 0; xfLen_ = 256; xfRho_ = 1.0f;
                        }
                    }
                }

                // --- the splice: every D output samples jump back one cycle L and crossfade over min((WIDTH+1) L, D) ---
                if (spliceOn && !cueOn_ && !vsOnly)
                {
                    evCount_ -= 1.0;
                    if (evCount_ <= 0.0)
                    {
                        if (xfPos_ < xfLen_) { anaPos_ = hB_; xfPos_ = xfLen_; }
                        int L = cycleFixed;
                        if (useSearch)
                        {
                            if (lagCache_ <= 0 || sinceSearch_ >= searchEvery)
                            {
                                lagCache_ = searchLag((int64_t)std::llround(anaPos_), nPts, std::min(dPerL, (double)widthMul), wCap, lMin, lMax, clean ? lFloor : 0);
                                sinceSearch_ = 0;
                            }
                            L = lagCache_;
                        }
                        const double D = (double)L * dPerL;
                        const double X = std::min((double)widthMul * (double)L, D);
                        hB_ = anaPos_ - (double)L;                               // jump back one cycle
                        if (looping_) hB_ = wrapLoop(hB_);
                        xfLen_ = std::max(1, (int)std::lround(X / q));
                        // How alike are the two streams over the crossfade? Alike (a well matched cycle): a plain linear fade keeps the level.
                        // Unlike (noise, a transient): a linear fade dips about 3 dB in the middle, so those get an equal-power fade.
                        {
                            double saa = 0.0, sbb = 0.0, sab = 0.0;
                            const int span = std::min(xfLen_, 4096);
                            for (int k = 0; k < span; k += 4)
                            {
                                const double a = (double)monoI((int64_t)std::llround(anaPos_ + (double)k * q));
                                const double b = (double)monoI((int64_t)std::llround(hB_ + (double)k * q));
                                saa += a * a; sbb += b * b; sab += a * b;
                            }
                            xfRho_ = (float)mpc::clamp(sab / std::sqrt(saa * sbb + 1e-12), 0.0, 1.0);
                        }
                        xfPos_ = 0;
                        evCount_ += D / q;
                    }
                    if (sinceSearch_ < (1 << 30)) ++sinceSearch_;
                }

                // --- the output of the splice engine: stream A, crossfading into stream B ---
                float wet[2] = {rd(0, anaPos_), rd(1, anaPos_)};
                if (xfPos_ < xfLen_)
                {
                    const float g = (float)(xfPos_ + 1) / (float)xfLen_;
                    const float ang = 1.5707963f * g;
                    const float gB = (1.0f - xfRho_) * std::sin(ang) + xfRho_ * g;
                    const float gA = (1.0f - xfRho_) * std::cos(ang) + xfRho_ * (1.0f - g);
                    const float b0 = rd(0, hB_), b1 = rd(1, hB_);
                    wet[0] = wet[0] * gA + b0 * gB;
                    wet[1] = wet[1] * gA + b1 * gB;
                    if (++xfPos_ >= xfLen_) anaPos_ = hB_;
                }

                if (vsLoop_.running && vsMix_ > 1e-4f)
                {
                    float v[2];
                    vsLoop_.tick(*this, vsR, vsF, std::fabs(vsF - 1.0) < 1e-6, v);
                    wet[0] += (v[0] - wet[0]) * vsMix_;
                    wet[1] += (v[1] - wet[1]) * vsMix_;
                }

                // --- Cue: a slice repeated ---
                pauseMix_ += (pauseTarget - pauseMix_) * 0.01f;
                if (pauseMix_ > 1e-4f)
                {
                    const int outLen = speedWanted ? sliceOut : sliceLen_;
                    float env = 1.0f;
                    if (slicePhase_ < kFadeSamples) env = (float)slicePhase_ / (float)kFadeSamples;
                    else if (outLen - slicePhase_ < kFadeSamples) env = (float)(outLen - slicePhase_) / (float)kFadeSamples;
                    float s0, s1;
                    if (speedWanted)
                    {
                        // the stutter at another speed: the slice is replayed by the Speed player, so it repeats faster or slower
                        if (slicePhase_ == 0 || !vsCue_.running)
                        {
                            vsCue_.wrap = true; vsCue_.lo = sliceS0_; vsCue_.hi = sliceS0_ + (double)cueLen;
                            vsCue_.start(sliceS0_);
                        }
                        float v[2];
                        vsCue_.tick(*this, cueR, cueF, std::fabs(cueF - 1.0) < 1e-6, v);
                        s0 = v[0] * env; s1 = v[1] * env;
                    }
                    else
                    {
                        vsCue_.running = false;
                        double p = sliceS0_ + (double)slicePhase_;
                        if (looping_) { const double L = (double)(B_ - A_); if (L >= 1.0) while (p >= (double)B_) p -= L; }
                        s0 = rd(0, p) * env; s1 = rd(1, p) * env;
                    }
                    wet[0] = wet[0] * (1.0f - pauseMix_) + s0 * pauseMix_;
                    wet[1] = wet[1] * (1.0f - pauseMix_) + s1 * pauseMix_;
                    if (++slicePhase_ >= outLen)
                    {
                        slicePhase_ = 0;
                        sliceS0_ = pendS0_;
                        sliceLen_ = cueLen;
                    }
                }
                for (int c = 0; c < 2; ++c) sig[c] = x[c] + (wet[c] - x[c]) * stretchGain_;
            }

            // --- true sample-rate reduction ---
            if (rateOn)
            {
                rateAcc_ += rateStep;
                if (rateAcc_ >= 1.0) { rateAcc_ -= 1.0; held_[0] = sig[0]; held_[1] = sig[1]; }
                sig[0] = held_[0]; sig[1] = held_[1];
            }

            // --- bit depth (24 = untouched) ---
            if (bitsOn)
                for (int c = 0; c < 2; ++c)
                    sig[c] = std::floor(mpc::clamp(sig[c], -1.0f, 1.0f) * bitLevels + 0.5f) / bitLevels;

            // --- S950 low-pass: three trapezoidal state-variable sections = a 6th-order Butterworth (-36 dB/oct) ---
            if (filterOn)
            {
                gSmooth_ += (gTarget - gSmooth_) * 0.004f;
                const float g = gSmooth_;
                float a1[3], a2[3], a3[3];
                for (int k = 0; k < 3; ++k) { a1[k] = 1.0f / (1.0f + g * (g + kSec[k])); a2[k] = g * a1[k]; a3[k] = g * a2[k]; }
                for (int c = 0; c < 2; ++c)
                {
                    float* z = ladder_[c];
                    float x = sig[c];
                    for (int k = 0; k < 3; ++k)                          // three trapezoidal state-variable sections
                    {
                        float& ic1 = z[2 * k];
                        float& ic2 = z[2 * k + 1];
                        const float v3 = x - ic2;
                        const float v1 = a1[k] * ic1 + a2[k] * v3;
                        const float v2 = ic2 + a2[k] * ic1 + a3[k] * v3;
                        ic1 = 2.0f * v1 - ic1;
                        ic2 = 2.0f * v2 - ic2;
                        if (std::fabs(ic1) < 1e-18f) ic1 = 0.0f;         // no denormals in the feedback path
                        if (std::fabs(ic2) < 1e-18f) ic2 = 0.0f;
                        x = v2;
                    }
                    sig[c] = x;
                }
            }
            else
            {
                gSmooth_ = gTarget;
                for (int c = 0; c < 2; ++c) for (int k = 0; k < 6; ++k) ladder_[c][k] = 0.0f;
            }

            for (int c = 0; c < nch; ++c) ctx.outputs[c][i] = sig[c];
        }
        totalSamples_ += n;

        // ---- the Punch keys light up with the real state (lit = set / running) -------------------------
        syncState(kPunchIn, haveA_, shownIn_, lastIn_);                   // lit: a start is set
        syncState(kPunchOut, loopDefined_, shownOut_, lastOut_);          // lit: the loop is defined (running or stopped)
        syncState(kLoopRun, looping_, shownRun_, lastRun_);               // lit: the loop is running
        syncState(kSpeedLive, looping_ || cueOn_, shownLive_, lastLive_); // Speed is only active while a loop runs or Cue is on
    }

private:
    static mpc::PluginInfo makeInfo()
    {
        mpc::PluginInfo info;
        info.name         = "Z950";
        info.vendor       = "Keebz";
        info.uniqueId     = MPC_FOURCC(kUid[0], kUid[1], kUid[2], kUid[3]);
        info.version      = 1000;
        info.isInstrument = false;
        info.numInputs    = 2;
        info.numOutputs   = 2;
        info.tailSamples  = 1;
        return info;
    }

    static constexpr char kUid[5] = "KhRP";

    // ---- keeping the host's screen in step with changes the plugin makes itself -----------------------------
    void markDirty(int index) { dirty_.fetch_or(1u << index, std::memory_order_relaxed); }
    // write the key only when the plugin's own state CHANGED (so a state load is never overwritten)
    void syncState(int index, bool on, bool& shown, bool& last)
    {
        if (on != shown)
        {
            shown = on;
            if (getBool(index) != on) setNormalised(index, on ? 1.0f : 0.0f);
            markDirty(index);
        }
        last = getBool(index);
    }
    void notifierLoop()
    {
        while (!stopNotifier_.load())
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(25));
            uint32_t m = dirty_.exchange(0, std::memory_order_relaxed);
            for (int i = 0; m != 0 && i < kNumParams; ++i)
                if (m & (1u << i)) notifyHostParameterChanged(i);
        }
    }

    // The S950 filter's cutoff for the Filter value F (0..99, the S950's own scale). From the S950 v1.2b ROM (voice start routine): the index
    // 70 + floor(1.25 * F) (+ key follow and velocity terms, which an effect does not have) is clamped to 98..170 and looked up in a byte table of
    // clock dividers N that is written to the voice's filter clock counter. The filter chip (MF6CN-50, 6th-order Butterworth) cuts off at
    // fclk / 49.27 with fclk = master / N. F up to about 22 all land on the bottom index (the cutoff sits at ~314 Hz, the forum figure is "about
    // 300 Hz"), F from about 80 on on the top one (~20 kHz). The master clock is not in the ROM: 3.95 MHz fits both ends.
    static double s950Cutoff(int f)
    {
        static const unsigned char kDiv[73] = {      // the ROM's byte table (0x9b44 + index), index 98 .. 170
            255, 241, 227, 214, 202, 191, 180, 170, 161, 152, 143, 135, 128, 120, 114, 107, 101, 96, 90, 85, 80, 76, 72, 68, 64, 60, 57, 54, 51,
            48, 45, 43, 40, 38, 36, 34, 32, 30, 28, 27, 25, 24, 23, 21, 20, 19, 18, 17, 16, 15, 14, 13, 13, 12, 11, 11, 10, 9, 9, 8, 8, 8, 7, 7, 6,
            6, 6, 5, 5, 5, 5, 5, 4 };
        const int idx = mpc::clamp(70 + (f * 320) / 256, 98, 170);
        return 3.95e6 / (double)kDiv[idx - 98] / 49.27;
    }
    static inline float softClip(float x)           // cheap tanh
    {
        x = mpc::clamp(x, -3.0f, 3.0f);
        return x * (27.0f + x * x) / (27.0f + 9.0f * x * x);
    }

    // ---- ring access (positions wrap inside the loop while looping) -----------------------------------------
    inline double wrapLoop(double p) const
    {
        if (looping_ && B_ > A_)
        {
            const double L = (double)(B_ - A_);
            while (p >= (double)B_) p -= L;
            while (p < (double)A_) p += L;
        }
        return p;
    }
    inline int64_t wrapLoopI(int64_t p) const
    {
        if (looping_ && B_ > A_)
        {
            const int64_t L = B_ - A_;
            while (p >= B_) p -= L;
            while (p < A_) p += L;
        }
        return p;
    }
    // Inside a rotated loop the loop's start has been moved by rot_: a position v of the (virtual) loop [A_, B_) reads the ring at
    // A_ + ((v - A_ + rot_) mod fullLen_).
    inline int64_t realIdx(int64_t v) const
    {
        if (!looping_ || rot_ == 0 || fullLen_ <= 0) return v;
        int64_t m = (v - A_ + rot_) % fullLen_;
        if (m < 0) m += fullLen_;
        return A_ + m;
    }
    inline float monoI(int64_t i) const { return mono_[(size_t)(realIdx(wrapLoopI(i)) & mask_)]; }

    // Sum of absolute differences between the audio and itself shifted by `lag`, over n evenly spaced points of a window
    // of lag * wMult samples (capped) that starts at p. This is the S1000's comparison.
    double sad(int64_t p, int lag, int n, double wMult, int wCap) const
    {
        const double W = std::min((double)lag * wMult, (double)wCap);
        const int stride = std::max(1, (int)(W / (double)n));
        double sum = 0.0;
        for (int k = 0; k < n; ++k)
        {
            const int64_t pos = p + (int64_t)k * stride;
            sum += std::fabs((double)monoI(pos) - (double)monoI(pos - lag));
        }
        return sum;
    }

    // The S1000 INTELL search (v4.4 ROM): coarse pass over lags lMin+4, lMin+12, ... (step 8, n points each); every coarse
    // candidate whose SAD x 0.75 can still beat the best so far is refined at step 2 over the four lags lMin+8j .. lMin+8j+6
    // (2n points, halved).
    // Addition (not in the ROM): the raw SAD favours the shortest lag on any sound without a clear pitch (hi-hats, a drum
    // break): neighbouring samples are always alike, so the search ends on the floor, a 1 ms cycle, and the splice becomes a
    // continuous 1 ms comb filter. When that happens the search is repeated for lags of at least `floor` (5 ms), so the
    // inserted cycle is a real stretch of the sound. A tonal sound has its true period well above the floor and is unaffected.
    int searchLagRange(int64_t p, int n, double wMult, int wCap, int lMin, int lMax) const
    {
        double coarse[kMaxCoarse];
        const int nC = std::min(kMaxCoarse, (lMax + 1 - lMin) >> 3);
        for (int j = 0; j < nC; ++j) coarse[j] = sad(p, lMin + 4 + 8 * j, n, wMult, wCap);
        double best = 1e300;
        int bestLag = lMin;
        for (int j = 0; j < nC; ++j)
        {
            if (coarse[j] * 0.75 >= best) continue;
            for (int t = 0; t < 4; ++t)
            {
                const int lag = lMin + 8 * j + 2 * t;
                const double sadv = sad(p, lag, 2 * n, wMult, wCap) * 0.5;
                if (sadv < best) { best = sadv; bestLag = lag; }
            }
        }
        return bestLag;
    }
    int searchLag(int64_t p, int n, double wMult, int wCap, int lMin, int lMax, int floor) const
    {
        int lag = searchLagRange(p, n, wMult, wCap, lMin, lMax);
        if (lag <= lMin + 8 && floor > lMin + 16 && floor < lMax - 16) lag = searchLagRange(p, n, wMult, wCap, floor, lMax);
        return lag;
    }

    inline float rd(int c, double p) const
    {
        const int64_t i = (int64_t)std::floor(p);
        const float   f = (float)(p - (double)i);
        const float*  r = ring_[c].data();
        const float   a = r[(size_t)(realIdx(i) & mask_)];
        const float   b = r[(size_t)(realIdx(i + 1) & mask_)];
        return a + (b - a) * f;
    }

    // ---- Speed player: overlap-add of Hann grains read from the ring (or the loop / the cue slice) -----------------------
    // Grains start every hop = len / 2 output samples; grain k reads from the analysis position ana + k * R * hop at f source samples per
    // output sample (f = 1 keeps the pitch; the grain start is aligned to the previous grain's natural continuation, WSOLA style). R is
    // read again at every grain start, so a new Speed is heard within about 15 ms.
    struct VarSpeed
    {
        struct Grain { double pos = 0.0; int age = 0; bool on = false; };
        Grain g[2];
        std::vector<float> win;
        int len = 0, hop = 0, next = 0;
        double ana = 0.0, prev = 0.0, cur = 0.0, lo = 0.0, hi = 0.0;
        bool havePrev = false, running = false, wrap = false;

        void setup(double sr)
        {
            len = std::max(64, ((int)std::lround(0.032 * sr) / 2) * 2);
            hop = len / 2;
            win.assign((size_t)len, 0.0f);
            for (int i = 0; i < len; ++i) win[(size_t)i] = 0.5f - 0.5f * (float)std::cos(6.283185307179586 * (double)i / (double)len);
            running = false;
        }
        // begin at `pos` with the first grain already at its loudest, so a restart has no fade-in gap
        void start(double pos)
        {
            g[0].pos = pos; g[0].age = hop; g[0].on = true;
            g[1].on = false;
            ana = pos; cur = pos; next = 0;
            havePrev = false; running = true;
        }
        double wrapPos(const DeepStretch& o, double p) const
        {
            if (wrap && hi > lo)
            {
                const double L = hi - lo;
                p = lo + std::fmod(p - lo, L);
                if (p < lo) p += L;
            }
            if (o.looping_) p = o.wrapLoop(p);
            return p;
        }
        double align(const DeepStretch& o, double a) const
        {
            if (!havePrev) return a;
            const double t = prev + (double)hop;                 // where the previous grain would carry on
            const int rad = hop / 2;
            double best = 1e300; int bestD = 0;
            // candidates in order of distance from the plain position, so a tie (silence, a perfectly periodic sound) keeps the grain where it is
            for (int step = 0; step <= rad; step += 2)
                for (int sgn = (step == 0 ? 1 : -1); sgn <= 1; sgn += 2)
                {
                    const int d = step * sgn;
                    double sum = 0.0;
                    for (int k = 0; k < hop; k += 4)
                        sum += std::fabs((double)o.monoI((int64_t)std::floor(wrapPos(o, t + k))) - (double)o.monoI((int64_t)std::floor(wrapPos(o, a + d + k))));
                    if (sum < best * 0.9999) { best = sum; bestD = d; }
                }
            return a + (double)bestD;
        }
        void tick(const DeepStretch& o, double R, double f, bool doAlign, float* out)
        {
            if (next <= 0)
            {
                const int slot = !g[0].on ? 0 : (!g[1].on ? 1 : (g[0].age > g[1].age ? 0 : 1));
                const double src = wrapPos(o, doAlign ? align(o, ana) : ana);
                g[slot].pos = src; g[slot].age = 0; g[slot].on = true;
                prev = src; havePrev = true;
                ana = wrapPos(o, ana + R * (double)hop);
                next += hop;
            }
            --next;
            out[0] = out[1] = 0.0f;
            double newest = cur; int youngest = 1 << 30;
            for (int k = 0; k < 2; ++k)
            {
                Grain& gr = g[k];
                if (!gr.on) continue;
                const float w = win[(size_t)gr.age];
                const double p = wrapPos(o, gr.pos);
                out[0] += o.rd(0, p) * w;
                out[1] += o.rd(1, p) * w;
                if (gr.age < youngest) { youngest = gr.age; newest = p; }
                gr.pos += f;
                if (++gr.age >= len) gr.on = false;
            }
            cur = newest;
        }
    };
    VarSpeed vsLoop_, vsCue_;

    double sampleRate_ = 44100.0;
    std::vector<float> ring_[2];
    std::vector<float> mono_;
    int64_t ringSize_ = 0, mask_ = 0, guard_ = 0;
    int64_t writeAbs_ = 0;
    int64_t totalSamples_ = 0;

    // splice engine: stream A at anaPos_, stream B at hB_ (crossfading in), events every D output samples
    double  anaPos_ = 0.0, hB_ = 0.0;
    int     xfPos_ = 0, xfLen_ = 0;
    double  evCount_ = 1.0;
    int     lagCache_ = 0, sinceSearch_ = 0;
    float   stretchGain_ = 0.0f;
    float   xfRho_ = 1.0f;                     // 1 = the two crossfaded streams are alike (linear fade), 0 = unrelated (equal-power fade)

    // loop
    bool    looping_ = false, armed_ = false, haveA_ = false, frozen_ = false;
    int64_t A_ = 0, B_ = 0, armB_ = 0;
    float   lenBeats_ = 0.0f;
    int     lastLoopLen_ = 0;
    bool    lastIn_ = false, lastOut_ = false, lastRun_ = false;
    bool    shownIn_ = false, shownOut_ = false, shownRun_ = false;     // state last written to the keys
    bool    loopDefined_ = false;                    // A_ / B_ hold a loop (running or stopped)
    int64_t fullLen_ = 0, rot_ = 0;                  // the whole loop (1/1) and how far its start has been rotated by Cue + Jog
    int     lastTotal_ = 0;
    bool    loopFree_ = false;                       // the running loop was tapped in Free mode (not tied to the master tempo)
    double  freeLen_ = 0.0, shownBpm_ = 0.0;
    std::atomic<bool> bpmValid_{false};

    // cue / jog
    bool    cueActive_ = false, cueOn_ = false;
    float   pauseMix_ = 0.0f;
    double  cuePos_ = 0.0, sliceS0_ = 0.0, pendS0_ = 0.0;
    int     slicePhase_ = 0, sliceLen_ = 5512, jogRef_ = kJogCentre;

    bool    poweredOn_ = true;
    bool    lastModeSw_ = false;
    float   lastCyc_ = 2000.0f;
    bool    cueSpeedMode_ = false;
    bool    shownLive_ = false, lastLive_ = false;
    float   vsMix_ = 0.0f;
    bool    vsJumpPending_ = false;
    double  vsJumpPos_ = 0.0;
    float   ladder_[2][6] = {};                      // the filter's three state-variable sections per channel
    float   gSmooth_ = -1.0f;
    float   held_[2] = {0.0f, 0.0f};
    double  rateAcc_ = 0.0;

    // host notification helper
    std::thread notifier_;
    std::atomic<bool> stopNotifier_{false};
    std::atomic<uint32_t> dirty_{0};
};

MPC_PLUGIN_ENTRY(DeepStretch)
