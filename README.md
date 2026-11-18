# Z950

(by Keebz)

Insert effect for Akai MPC: live S-series style time stretch / pitch shift (Akai S1000/S3000 rack samplers, the 90s jungle sound),
a CD-deck Cue / Jog scrub and a tempo-matched Punch In / Punch Out looper. The screen is styled after an Akai S950 front panel,
and a HELP tab on the plugin explains every control.

Requires MPC OS 3.10.1+ with Preferences > Enhancements (Beta) > Enable Enhancements + External Plugin Support.
Experimental, provided AS IS. Built with the inMusic MPC Plugin SDK (MIT). Original code, not affiliated with Akai.

| Control | Does |
|---|---|
| **POWER** key (top left) | Takes the plugin out of the circuit: audio passes straight through, no delay, no effect, any loop is dropped. The power symbol glows bright red while on. |
| **MODE** key (small key under POWER) | CYCLIC or INTELL stretch, as on the S1000. The outline turns red in INTELL mode; the first LCD column reads INTELL and the first knob becomes the ORIG / CLEAN style; Qual and Width are inactive (greyed, "--") in CYCLIC. Pitch works in both modes. |
| **Length** 100-2000 % | 100 = off. Above 100 stretches the live input without changing pitch; back to 100 snaps to live. With Pitch on the knob spans 100-300 % (finer). |
| **Cyclic / Style** | CYCLIC mode: length of the cycle that is inserted (0 = Auto, searched like INTELL). INTELL mode: the same knob is the STYLE, ORIG (the S1000 lag search exactly as the ROM has it) or CLEAN (default; avoids the 1 ms comb on drums). Each mode keeps its own value. |
| **Qual** 0-100 | INTELL: QUAL+1 comparison points when searching for the best cycle. |
| **Width** 0-100 | INTELL: crossfade of (WIDTH+1) cycles, up to the whole gap between insertions. |
| **Bit** 8/12/16/24 | Output bit depth; all the way right (24) is untouched. |
| **Rate** 8000-44100 Hz | True sample-rate reduction. |
| **Filter** 0-99 | The Akai S900/S950 low-pass, 1:1, last in the chain: a 6th-order Butterworth (-36 dB/oct, no resonance; National MF6-50 in the original) on the S950's own 0-99 scale and cutoff law, read from the S950 v1.2b ROM (index 70 + floor(1.25 F) clamped to 98..170, integer clock dividers): 0 to ~22 = 314 Hz, 22 to 80 = six octaves up to ~20 kHz, above 80 = open. Not modelled: the chip's clock feedthrough and its aliasing around the clock frequency. |
| **Pitch** | On: Length shifts pitch (stretch then resample, duration stays; 200 = +1 octave). The PITCH header is greyed while off. |
| **Speed** -100..+100 | Turntable-style speed (0 = normal; the knob catches at 0, inside +-3 it snaps to 0; a new loop resets it to 0; +100 = twice as fast, -100 = stopped) of the audio stored in the looper and of the Cue stutter only; it acts at once and is greyed out (--) while no loop is running and Cue is off. Pitch off keeps the pitch (overlap-add player, about 30 ms grains); Pitch on makes the pitch follow. In Cue the stutter repeats faster or slower. |
| **Cue** | Stutters the last 1/8 s; press again to go back to live. In a loop, releasing Cue moves the loop's start to where the stutter began (Cue on, Jog to the new start, Cue off): the loop rotates inside its own audio. Lit while on. |
| **Jog** | While Cue is on, one step = one CD frame (13 ms), +-400 frames (about 5 s) from where Cue was pressed. Touch-drag, main encoder or Q-Link. For the touch strip: the MPC sends no MIDI to effect plugins, so put the strip in Crossfader mode and assign the Jog parameter to it in Q-Link Edit. |
| **Punch In / Out** | Loop start / end. In is lit while a start is set, Out while a loop exists; Out again throws the loop away. |
| **Stop / Start** | Stops the loop WITHOUT dumping it (live audio comes back) and starts the same loop again from its start. A stopped loop is kept for about 40 s. The loop's BPM is shown above the three keys. |
| **Loop dial** | FREE, 1/1, 1/2, 1/4, 1/8, 1/16, 1/32, 1/64. A loop tapped with the dial on FREE is not tied to the sequence tempo: it counts as 1/1, its BPM is shown, and turning the dial cuts it to that fraction of its own length, measured from its start, restarting playback there. A length chosen before punching in makes a tempo-locked loop (snaps to the grid, follows tempo changes). |

Screen order: Cyclic/Intell, Length, Qual, Width, Bit, Rate, Filter, Pitch. Q-Link pages follow it: 1 = Cyclic Length Qual Width, 2 = Bit Rate Filter Pitch, 3 = Jog wheel + Speed, 4 = Loop dial.
Hold Shift while turning a Q-Link or the main encoder for finer steps (most useful on Length, Cyclic, Rate, Filter and Jog).
The HELP tab has two pages (press the HELP key again for page 2).

## How the stretch works (from the S1000 v4.4 firmware)
Stretching by a factor s inserts one cycle of length L every D = L*s/(s-1) samples; the read position jumps back by L and the two
read positions are crossfaded over min((WIDTH+1)*L, D). CYCLIC: L is the Cyclic value. INTELL: L is the lag (40-2000 samples at 44.1 kHz) at which
the audio best matches itself, found by a sum-of-absolute-differences search (QUAL+1 points, coarse step 8 then step 2). Written
from scratch; no Akai code or data is included.

## Status
- Desktop verified: host simulator (20 passed), DSP tests (stretch keeps pitch in both modes, INTELL is smoother than CYCLIC on harmonic
  material, pitch-on Length remap, loops at 1/4..1/64, cue 1/4 and 1/8 s repeats, lit keys), INTELL about 1 % of real time on a PC.
- NOT verified on a real MPC: screen drawing, touch, Q-Link pages, the host refreshing the screen when the plugin changes a parameter
  itself (done from a small helper thread), and INTELL CPU load on the MPC.
- The comparison window is capped at 2048 samples (the firmware's is 16384) to keep latency down; the stretch starts about 50-60 ms behind live.
- The skin is generated by `tools/make_skin.py` (Pillow) into `skins/`.

By Keebz  -  Keebz.com  -  Instagram: @LeeKebler  -  Github: Github.com/Keebz

Licence: MIT. SDK credit: https://github.com/inmusic-software/mpc-plugin-builder-sdk

## INTELL notes

The INTELL search follows the Akai S1000 v4.4 ROM: lags 40..2000 samples at 44.1 kHz, 2 x (QUAL+1) comparison points, a window of
lag x min(D/L, WIDTH+1) samples, a coarse pass at step 8 and a step-2 refinement, then a linear crossfade of
min((WIDTH+1) x L, D) samples. Two differences are there for live use (the comparison window is capped at 2048 samples, and the
lag is searched about every 8 ms). One is an addition: the ROM's raw difference sum favours the shortest lag on sounds without
a clear pitch (hi-hats, drum breaks), which turns the splice into a continuous 1 ms comb filter ("washy"). When the search ends on
the shortest lags it is repeated for lags of at least 5 ms.
