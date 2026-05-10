# SFML minimp3 Heap Buffer Overflow

## Metadata

- GitHub Security Advisory: https://github.com/SFML/SFML/security/advisories/GHSA-hq2x-cpx5-hmcm
- GHSA ID: `GHSA-hq2x-cpx5-hmcm`
- Reserved CVE ID: `CVE-2025-50940`
- Component: SFML Audio MP3 decoding, `sf::Music::openFromMemory()`, bundled `minimp3`
- PoC archive: `poc_sfml_minimp3_heap_buffer_overflow.zip`

We have received a reserved CVE identifier, `CVE-2025-50940`, for this vulnerability.

## Original Bug Description

### Summary
_Short summary of the problem. Make the impact and severity as clear as possible. For example: An unsafe deserialization vulnerability allows any unauthenticated user to execute arbitrary code on the server._

While fuzz testing the Audio (Music) module using LibFuzzer, I discovered a heap buffer overflow triggered by the music.openFromMemory() function. The crash originates from an incorrect length calculation in the minimp3 library used by SFML, which leads to out-of-bounds memory access.

This vulnerability allows an attacker to supply a specially crafted MP3 file that could potentially read or corrupt memory, affecting confidentiality and integrity if sensitive or adjacent data is exposed or overwritten. Additionally, it compromises availability by causing the application to crash. In more severe scenarios, this issue could be network-exploitable, enabling attackers to cause a denial of service (DoS) if an SFML-based application processes untrusted or remote media input.

### Details
_Give all details on the vulnerability. Pointing to the incriminated source code is very helpful for the maintainer._

Please see below for the call stack:
```
==166628==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x7f3b28f2d800 at pc 0x55dd30ea1785 bp 0x7ffe7c2da1b0 sp 0x7ffe7c2da1a8
READ of size 1 at 0x7f3b28f2d800 thread T0
    #0 0x55dd30ea1784 in hdr_valid(unsigned char const*) ~/SFML/extlibs/headers/minimp3/minimp3.h:266:12
    #1 0x55dd30e8fbba in mp3d_find_frame(unsigned char const*, int, int*, int*) ~/SFML/extlibs/headers/minimp3/minimp3.h:1666:13
    #2 0x55dd30e8e7f1 in mp3dec_decode_frame ~/SFML/extlibs/headers/minimp3/minimp3.h:1721:13
    #3 0x55dd30e9beff in mp3dec_load_index(void*, unsigned char const*, int, int, unsigned long, unsigned long, mp3dec_frame_info_t*) ~/SFML/extlibs/headers/minimp3/minimp3_ex.h:668:31
    #4 0x55dd30e9a453 in mp3dec_iterate_cb ~/SFML/extlibs/headers/minimp3/minimp3_ex.h:593:24
    #5 0x55dd30ea0cf4 in mp3dec_ex_open_cb ~/SFML/extlibs/headers/minimp3/minimp3_ex.h:996:15
    #6 0x55dd30ea29c2 in sf::priv::SoundFileReaderMp3::open(sf::InputStream&) ~/SFML/src/SFML/Audio/SoundFileReaderMp3.cpp:132:5
    #7 0x55dd30e67143 in sf::InputSoundFile::openFromMemory(void const*, unsigned long) ~/SFML/src/SFML/Audio/InputSoundFile.cpp:158:31
    #8 0x55dd30e4461d in sf::Music::openFromMemory(void const*, unsigned long) ~/SFML/src/SFML/Audio/Music.cpp:141:23
    #9 0x55dd30e3db23 in LLVMFuzzerTestOneInput ~/SFML/fuzz/fuzz_sound.cc:19:16
    #10 0x55dd30d63e13 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) (~/SFML/fuzz/fuzz_sound+0x6ee13) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #11 0x55dd30d63569 in fuzzer::Fuzzer::RunOne(unsigned char const*, unsigned long, bool, fuzzer::InputInfo*, bool, bool*) (~/SFML/fuzz/fuzz_sound+0x6e569) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #12 0x55dd30d64d59 in fuzzer::Fuzzer::MutateAndTestOne() (~/SFML/fuzz/fuzz_sound+0x6fd59) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #13 0x55dd30d658d5 in fuzzer::Fuzzer::Loop(std::vector<fuzzer::SizedFile, std::allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x708d5) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #14 0x55dd30d53a12 in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) (~/SFML/fuzz/fuzz_sound+0x5ea12) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #15 0x55dd30d7d702 in main (~/SFML/fuzz/fuzz_sound+0x88702) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #16 0x7f3b4fa29d8f in __libc_start_call_main csu/../sysdeps/nptl/libc_start_call_main.h:58:16
    #17 0x7f3b4fa29e3f in __libc_start_main csu/../csu/libc-start.c:392:3
    #18 0x55dd30d48454 in _start (~/SFML/fuzz/fuzz_sound+0x53454) (BuildId: 62f62e138546577d2e598cca70379925a4421631)

0x7f3b28f2d800 is located 0 bytes to the right of 131072-byte region [0x7f3b28f0d800,0x7f3b28f2d800)
allocated by thread T0 here:
    #0 0x55dd30e0048e in malloc (~/SFML/fuzz/fuzz_sound+0x10b48e) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #1 0x55dd30ea0ab5 in mp3dec_ex_open_cb ~/SFML/extlibs/headers/minimp3/minimp3_ex.h:987:40
    #2 0x55dd30ea29c2 in sf::priv::SoundFileReaderMp3::open(sf::InputStream&) ~/SFML/src/SFML/Audio/SoundFileReaderMp3.cpp:132:5
    #3 0x55dd30e67143 in sf::InputSoundFile::openFromMemory(void const*, unsigned long) ~/SFML/src/SFML/Audio/InputSoundFile.cpp:158:31
    #4 0x55dd30e4461d in sf::Music::openFromMemory(void const*, unsigned long) ~/SFML/src/SFML/Audio/Music.cpp:141:23
    #5 0x55dd30e3db23 in LLVMFuzzerTestOneInput ~/SFML/fuzz/fuzz_sound.cc:19:16
    #6 0x55dd30d63e13 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) (~/SFML/fuzz/fuzz_sound+0x6ee13) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #7 0x55dd30d63569 in fuzzer::Fuzzer::RunOne(unsigned char const*, unsigned long, bool, fuzzer::InputInfo*, bool, bool*) (~/SFML/fuzz/fuzz_sound+0x6e569) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #8 0x55dd30d64d59 in fuzzer::Fuzzer::MutateAndTestOne() (~/SFML/fuzz/fuzz_sound+0x6fd59) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #9 0x55dd30d658d5 in fuzzer::Fuzzer::Loop(std::vector<fuzzer::SizedFile, std::allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x708d5) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #10 0x55dd30d53a12 in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) (~/SFML/fuzz/fuzz_sound+0x5ea12) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #11 0x55dd30d7d702 in main (~/SFML/fuzz/fuzz_sound+0x88702) (BuildId: 62f62e138546577d2e598cca70379925a4421631)
    #12 0x7f3b4fa29d8f in __libc_start_call_main csu/../sysdeps/nptl/libc_start_call_main.h:58:16

SUMMARY: AddressSanitizer: heap-buffer-overflow ~/SFML/extlibs/headers/minimp3/minimp3.h:266:12 in hdr_valid(unsigned char const*)
Shadow bytes around the buggy address:
  0x0fe7e51ddab0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  0x0fe7e51ddac0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  0x0fe7e51ddad0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  0x0fe7e51ddae0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  0x0fe7e51ddaf0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
=>0x0fe7e51ddb00:[fa]fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0fe7e51ddb10: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0fe7e51ddb20: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0fe7e51ddb30: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0fe7e51ddb40: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0fe7e51ddb50: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
Shadow byte legend (one shadow byte represents 8 application bytes):
  Addressable:           00
  Partially addressable: 01 02 03 04 05 06 07 
  Heap left redzone:       fa
  Freed heap region:       fd
  Stack left redzone:      f1
  Stack mid redzone:       f2
  Stack right redzone:     f3
  Stack after return:      f5
  Stack use after scope:   f8
  Global redzone:          f9
  Global init order:       f6
  Poisoned by user:        f7
  Container overflow:      fc
  Array cookie:            ac
  Intra object redzone:    bb
  ASan internal:           fe
  Left alloca redzone:     ca
  Right alloca redzone:    cb
==166628==ABORTING
MS: 5 ShuffleBytes-CopyPart-EraseBytes-InsertByte-CrossOver-; base unit: 1360ba6ae98e3cd9fba85642be403e24fbbb831b
artifact_prefix='./'; Test unit written to ./crash-8c99c72c97586ff6cfa9ecf7a73540e25101bcb0
```
The issue appears to originate from the minimp3 library (used by SFML for MP3 decoding), specifically in extlibs/headers/minimp3/minimp3_ex.h at line 593. This callback eventually invokes mp3dec_load_index (line 616), which receives a pointer to the frame array along with its size (buf_size).

However, buf_size is incorrectly calculated at line 583. The hdr pointer is derived from the buf array, shifted by consumed + i. When passing the size of the remaining buffer to mp3dec_load_index, the i offset is not subtracted, causing the function to access memory beyond the actual bounds of the array, leading to a heap-buffer-overflow.

A potential fix would be subtracting i from the calculated length before passing it as buf_size (see snippet below). Since the upstream repository lieff/minimp3 has not seen active maintenance for over two years, we may not be able to report this directly. However, we can fix this for SFML by patching it's local copy.

Potential Fix:
```
diff --git a/extlibs/headers/minimp3/minimp3_ex.h b/extlibs/headers/minimp3/minimp3_ex.h
index 2871705d..69755972 100644
--- a/extlibs/headers/minimp3/minimp3_ex.h
+++ b/extlibs/headers/minimp3/minimp3_ex.h
@@ -590,7 +590,7 @@ int mp3dec_iterate_cb(mp3dec_io_t *io, uint8_t *buf, size_t buf_size, MP3D_ITERA
         readed += i;
         if (callback)
         {
-            if ((ret = callback(user_data, hdr, frame_size, free_format_bytes, filled - consumed, readed, &frame_info)))
+            if ((ret = callback(user_data, hdr, frame_size, free_format_bytes, filled - consumed - i, readed, &frame_info)))
                 return ret;
         }
         readed += frame_size;
```

### PoC
_Complete instructions, including specific configuration details, to reproduce the vulnerability._

The test was performed on the latest master branch of SFML as of April 30, 2025 (commit b95b764). While the root cause lies in the bundled minimp3 library, the issue is fully reproducible through SFML’s public API and affects all versions that include minimp3.

A reproduction script is included here. Please unzip this file under the root directory of SFML, and simply run the script fuzz_crash_demo/demo_crash.sh. It allows you to toggle between “Buggy” and “Fixed” behavior to demonstrate the effect of the proposed patch.
[fuzz_crash_demo.zip](https://github.com/user-attachments/files/19980309/fuzz_crash_demo.zip)

AddressSanitizer was enabled during testing to ensure the bug is reliably triggered. Without ASan, the crash is non-deterministic — sometimes resulting in a segmentation fault, but more often silently accessing invalid memory, posing a potential security risk.

### Impact
_What kind of vulnerability is it? Who is impacted?_

This is a heap buffer overflow vulnerability, which leads to out-of-bounds memory access when processing a malformed MP3 file. Any application that uses SFML and accepts untrusted or user-supplied MP3 input is potentially affected. An attacker could exploit this issue by providing a specially crafted MP3 file, which may result in:

- Denial of Service (DoS) by crashing the application (availability impact)
- Memory disclosure or memory corruption, affecting confidentiality and integrity
- Potential for remote exploitation if the application processes MP3 files over the network (e.g., multiplayer games, media apps, online platforms using SFML)

No special privileges are required to exploit this vulnerability, and it does not require user interaction beyond loading the malicious file.
