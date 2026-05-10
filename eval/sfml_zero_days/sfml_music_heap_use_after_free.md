# SFML sf::Music Heap Use After Free

## Metadata

- Report: https://github.com/SFML/SFML/issues/3503
- Component: SFML Audio, `sf::Music`, `sf::SoundStream`, miniaudio audio callback
- PoC archive: `poc_sfml_music_heap_use_after_free.zip`
- Status: fixed by https://github.com/SFML/SFML/pull/3522

## Original Bug Description

### Prerequisite Checklist

- [x] I searched for [existing issues](https://github.com/search?q=repo%3ASFML%2FSFML&type=issues) to prevent duplicates
- [x] I searched for [existing discussions on the forum](https://www.google.com/search?q=site%3Ahttps%3A%2F%2Fen.sfml-dev.org) to prevent duplicates
- [x] I am here to report an issue and not to just ask a question or look for help (use the [forum](https://en.sfml-dev.org/forums/index.php#c3) or [Discord](https://discord.gg/nr4X7Fh) instead)

### Describe your issue here

While fuzzing SFML with libFuzzer, I encountered a heap-use-after-free bug in the sf::Music class. Please see the attached core dump for details.

```
==1714327==ERROR: AddressSanitizer: heap-use-after-free on address 0x60e0000009e0 at pc 0x000000585666 bp 0x7f53b2351650 sp 0x7f53b2351648
READ of size 8 at 0x60e0000009e0 thread T9
    #0 0x585665 in std::__uniq_ptr_impl<sf::SoundFileReader, std::default_delete<sf::SoundFileReader> >::_M_ptr() const /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/unique_ptr.h:173:42
    #1 0x585604 in std::unique_ptr<sf::SoundFileReader, std::default_delete<sf::SoundFileReader> >::get() const /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/unique_ptr.h:422:21
    #2 0x584014 in std::unique_ptr<sf::SoundFileReader, std::default_delete<sf::SoundFileReader> >::operator bool() const /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/unique_ptr.h:436:16
    #3 0x583e73 in sf::InputSoundFile::read(short*, unsigned long) ~/SFML/src/SFML/Audio/InputSoundFile.cpp:304:5
    #4 0x55f4e3 in sf::Music::onGetData(sf::SoundStream::Chunk&) ~/SFML/src/SFML/Audio/Music.cpp:271:62
    #5 0x58e461 in sf::SoundStream::Impl::read(void*, void*, unsigned long, unsigned long*) ~/SFML/src/SFML/Audio/SoundStream.cpp:99:37
    #6 0x6d44e8 in ma_data_source_read_pcm_frames_within_range(void*, void*, unsigned long, unsigned long*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:57220:18
    #7 0x6d2feb in ma_data_source_read_pcm_frames ~/SFML/extlibs/headers/miniaudio/miniaudio.h:57335:18
    #8 0x77e35b in ma_engine_node_process_pcm_frames__sound(void*, float const**, unsigned int*, float**, unsigned int*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:74404:22
    #9 0x77b410 in ma_node_process_pcm_frames_internal(void*, float const**, unsigned int*, float**, unsigned int*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:72510:9
    #10 0x6eef1a in ma_node_read_pcm_frames(void*, unsigned int, float*, unsigned int, unsigned int*, unsigned long) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:72614:9
    #11 0x77be55 in ma_node_input_bus_read_pcm_frames(void*, ma_node_input_bus*, float*, unsigned int, unsigned int*, unsigned long) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:71758:30
    #12 0x6ef29b in ma_node_read_pcm_frames(void*, unsigned int, float*, unsigned int, unsigned int*, unsigned long) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:72632:22
    #13 0x6ee307 in ma_node_graph_read_pcm_frames ~/SFML/extlibs/headers/miniaudio/miniaudio.h:71289:22
    #14 0x705372 in ma_engine_read_pcm_frames ~/SFML/extlibs/headers/miniaudio/miniaudio.h:75264:14
    #15 0x606894 in sf::priv::AudioDevice::initialize()::$_3::operator()(ma_device*, void*, void const*, unsigned int) const ~/SFML/src/SFML/Audio/AudioDevice.cpp:491:37
    #16 0x6067eb in sf::priv::AudioDevice::initialize()::$_3::__invoke(ma_device*, void*, void const*, unsigned int) ~/SFML/src/SFML/Audio/AudioDevice.cpp:485:41
    #17 0x76348a in ma_device__on_data_inner(ma_device*, void*, void const*, unsigned int) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:18690:5
    #18 0x762d5b in ma_device__on_data(ma_device*, void*, void const*, unsigned int) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:18771:25
    #19 0x76157e in ma_device__handle_data_callback(ma_device*, void*, void const*, unsigned int) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:18823:17
    #20 0x63ee36 in ma_device__read_frames_from_client(ma_device*, unsigned int, void*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:18926:21
    #21 0x63bbb2 in ma_device_handle_backend_data_callback ~/SFML/extlibs/headers/miniaudio/miniaudio.h:42531:13
    #22 0x745f96 in ma_device_write_to_stream__pulse(ma_device*, ma_pa_stream*, unsigned long*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:30145:17
    #23 0x744e8c in ma_device_on_write__pulse(ma_pa_stream*, unsigned long, void*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:30210:18
    #24 0x7f53d4e9491d  (/lib/x86_64-linux-gnu/libpulse.so+0x2e91d)
    #25 0x7f53d4b9bedf in pa_pdispatch_run (/usr/lib/x86_64-linux-gnu/pulseaudio/libpulsecommon-13.99.so+0x3dedf)
    #26 0x7f53d4e775f2  (/lib/x86_64-linux-gnu/libpulse.so+0x115f2)
    #27 0x7f53d4b9e946  (/usr/lib/x86_64-linux-gnu/pulseaudio/libpulsecommon-13.99.so+0x40946)
    #28 0x7f53d4ba172a  (/usr/lib/x86_64-linux-gnu/pulseaudio/libpulsecommon-13.99.so+0x4372a)
    #29 0x7f53d4ba1ae9  (/usr/lib/x86_64-linux-gnu/pulseaudio/libpulsecommon-13.99.so+0x43ae9)
    #30 0x7f53d4ba2379  (/usr/lib/x86_64-linux-gnu/pulseaudio/libpulsecommon-13.99.so+0x44379)
    #31 0x7f53d4e8cba2 in pa_mainloop_dispatch (/lib/x86_64-linux-gnu/libpulse.so+0x26ba2)
    #32 0x7f53d4e8ced1 in pa_mainloop_iterate (/lib/x86_64-linux-gnu/libpulse.so+0x26ed1)
    #33 0x74097b in ma_device_data_loop__pulse(ma_device*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:30816:20
    #34 0x63946f in ma_worker_thread(void*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:40910:13
    #35 0x73764e in ma_thread_entry_proxy(void*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:16508:14
    #36 0x7f53d7ee3608 in start_thread /build/glibc-FcRMwW/glibc-2.31/nptl/pthread_create.c:477:8
    #37 0x7f53d7c98352 in clone /build/glibc-FcRMwW/glibc-2.31/misc/../sysdeps/unix/sysv/linux/x86_64/clone.S:95

0x60e0000009e0 is located 0 bytes inside of 152-byte region [0x60e0000009e0,0x60e000000a78)
freed by thread T0 here:
    #0 0x5544ed in operator delete(void*) (~/SFML/fuzz/fuzz_sound+0x5544ed)
    #1 0x561256 in std::default_delete<sf::Music::Impl>::operator()(sf::Music::Impl*) const /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/unique_ptr.h:85:2
    #2 0x5603f6 in std::unique_ptr<sf::Music::Impl, std::default_delete<sf::Music::Impl> >::~unique_ptr() /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/unique_ptr.h:361:4
    #3 0x55d591 in sf::Music::~Music() ~/SFML/src/SFML/Audio/Music.cpp:100:1
    #4 0x557a64 in LLVMFuzzerTestOneInput ~/SFML/fuzz/fuzz_sound.cc:65:1
    #5 0x45d351 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) (~/SFML/fuzz/fuzz_sound+0x45d351)
    #6 0x45ca95 in fuzzer::Fuzzer::RunOne(unsigned char const*, unsigned long, bool, fuzzer::InputInfo*, bool*) (~/SFML/fuzz/fuzz_sound+0x45ca95)
    #7 0x45ea37 in fuzzer::Fuzzer::ReadAndExecuteSeedCorpora(std::__Fuzzer::vector<fuzzer::SizedFile, fuzzer::fuzzer_allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x45ea37)
    #8 0x45ec39 in fuzzer::Fuzzer::Loop(std::__Fuzzer::vector<fuzzer::SizedFile, fuzzer::fuzzer_allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x45ec39)
    #9 0x44e945 in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) (~/SFML/fuzz/fuzz_sound+0x44e945)
    #10 0x476592 in main (~/SFML/fuzz/fuzz_sound+0x476592)
    #11 0x7f53d7b9d082 in __libc_start_main /build/glibc-FcRMwW/glibc-2.31/csu/../csu/libc-start.c:308:16

previously allocated by thread T0 here:
    #0 0x553c8d in operator new(unsigned long) (~/SFML/fuzz/fuzz_sound+0x553c8d)
    #1 0x560227 in std::_MakeUniq<sf::Music::Impl>::__single_object std::make_unique<sf::Music::Impl>() /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/unique_ptr.h:962:30
    #2 0x55d1fe in sf::Music::Music() ~/SFML/src/SFML/Audio/Music.cpp:63:25
    #3 0x55689b in LLVMFuzzerTestOneInput ~/SFML/fuzz/fuzz_sound.cc:16:15
    #4 0x45d351 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) (~/SFML/fuzz/fuzz_sound+0x45d351)
    #5 0x45ca95 in fuzzer::Fuzzer::RunOne(unsigned char const*, unsigned long, bool, fuzzer::InputInfo*, bool*) (~/SFML/fuzz/fuzz_sound+0x45ca95)
    #6 0x45ea37 in fuzzer::Fuzzer::ReadAndExecuteSeedCorpora(std::__Fuzzer::vector<fuzzer::SizedFile, fuzzer::fuzzer_allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x45ea37)
    #7 0x45ec39 in fuzzer::Fuzzer::Loop(std::__Fuzzer::vector<fuzzer::SizedFile, fuzzer::fuzzer_allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x45ec39)
    #8 0x44e945 in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) (~/SFML/fuzz/fuzz_sound+0x44e945)
    #9 0x476592 in main (~/SFML/fuzz/fuzz_sound+0x476592)
    #10 0x7f53d7b9d082 in __libc_start_main /build/glibc-FcRMwW/glibc-2.31/csu/../csu/libc-start.c:308:16

Thread T9 created by T0 here:
    #0 0x50ea3a in pthread_create (~/SFML/fuzz/fuzz_sound+0x50ea3a)
    #1 0x7374b9 in ma_thread_create__posix(unsigned long*, ma_thread_priority, unsigned long, void* (*)(void*), void*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:16167:14
    #2 0x624d04 in ma_thread_create(unsigned long*, ma_thread_priority, unsigned long, void* (*)(void*), void*, ma_allocation_callbacks const*) ~/SFML/extlibs/headers/miniaudio/miniaudio.h:16542:14
    #3 0x635733 in ma_device_init ~/SFML/extlibs/headers/miniaudio/miniaudio.h:41968:18
    #4 0x601152 in sf::priv::AudioDevice::initialize() ~/SFML/src/SFML/Audio/AudioDevice.cpp:500:29
    #5 0x6009c5 in sf::priv::AudioDevice::AudioDevice() ~/SFML/src/SFML/Audio/AudioDevice.cpp:138:10
    #6 0x5fee5b in void __gnu_cxx::new_allocator<sf::priv::AudioDevice>::construct<sf::priv::AudioDevice>(sf::priv::AudioDevice*) /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/ext/new_allocator.h:156:23
    #7 0x5fea0f in void std::allocator_traits<std::allocator<sf::priv::AudioDevice> >::construct<sf::priv::AudioDevice>(std::allocator<sf::priv::AudioDevice>&, sf::priv::AudioDevice*) /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/alloc_traits.h:512:8
    #8 0x5fe4c6 in std::_Sp_counted_ptr_inplace<sf::priv::AudioDevice, std::allocator<sf::priv::AudioDevice>, (__gnu_cxx::_Lock_policy)2>::_Sp_counted_ptr_inplace<>(std::allocator<sf::priv::AudioDevice>) /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/shared_ptr_base.h:551:4
    #9 0x5fe065 in std::__shared_count<(__gnu_cxx::_Lock_policy)2>::__shared_count<sf::priv::AudioDevice, std::allocator<sf::priv::AudioDevice> >(sf::priv::AudioDevice*&, std::_Sp_alloc_shared_tag<std::allocator<sf::priv::AudioDevice> >) /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/shared_ptr_base.h:683:6
    #10 0x5fddb4 in std::__shared_ptr<sf::priv::AudioDevice, (__gnu_cxx::_Lock_policy)2>::__shared_ptr<std::allocator<sf::priv::AudioDevice> >(std::_Sp_alloc_shared_tag<std::allocator<sf::priv::AudioDevice> >) /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/shared_ptr_base.h:1376:14
    #11 0x5fdba7 in std::shared_ptr<sf::priv::AudioDevice>::shared_ptr<std::allocator<sf::priv::AudioDevice> >(std::_Sp_alloc_shared_tag<std::allocator<sf::priv::AudioDevice> >) /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/shared_ptr.h:408:4
    #12 0x5fd9a7 in std::shared_ptr<sf::priv::AudioDevice> std::allocate_shared<sf::priv::AudioDevice, std::allocator<sf::priv::AudioDevice> >(std::allocator<sf::priv::AudioDevice> const&) /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/shared_ptr.h:861:14
    #13 0x5fcf76 in std::shared_ptr<sf::priv::AudioDevice> std::make_shared<sf::priv::AudioDevice>() /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/shared_ptr.h:877:14
    #14 0x5fca91 in sf::AudioResource::AudioResource()::$_0::operator()() const ~/SFML/src/SFML/Audio/AudioResource.cpp:53:31
    #15 0x5fc842 in sf::AudioResource::AudioResource() ~/SFML/src/SFML/Audio/AudioResource.cpp:40:5
    #16 0x565d65 in sf::SoundSource::SoundSource() ~/SFML/include/SFML/Audio/SoundSource.hpp:656:5
    #17 0x58b22e in sf::SoundStream::SoundStream() ~/SFML/src/SFML/Audio/SoundStream.cpp:227:14
    #18 0x55d1be in sf::Music::Music() ~/SFML/src/SFML/Audio/Music.cpp:63:8
    #19 0x55689b in LLVMFuzzerTestOneInput ~/SFML/fuzz/fuzz_sound.cc:16:15
    #20 0x45d351 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) (~/SFML/fuzz/fuzz_sound+0x45d351)
    #21 0x45ca95 in fuzzer::Fuzzer::RunOne(unsigned char const*, unsigned long, bool, fuzzer::InputInfo*, bool*) (~/SFML/fuzz/fuzz_sound+0x45ca95)
    #22 0x45ea37 in fuzzer::Fuzzer::ReadAndExecuteSeedCorpora(std::__Fuzzer::vector<fuzzer::SizedFile, fuzzer::fuzzer_allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x45ea37)
    #23 0x45ec39 in fuzzer::Fuzzer::Loop(std::__Fuzzer::vector<fuzzer::SizedFile, fuzzer::fuzzer_allocator<fuzzer::SizedFile> >&) (~/SFML/fuzz/fuzz_sound+0x45ec39)
    #24 0x44e945 in fuzzer::FuzzerDriver(int*, char***, int (*)(unsigned char const*, unsigned long)) (~/SFML/fuzz/fuzz_sound+0x44e945)
    #25 0x476592 in main (~/SFML/fuzz/fuzz_sound+0x476592)
    #26 0x7f53d7b9d082 in __libc_start_main /build/glibc-FcRMwW/glibc-2.31/csu/../csu/libc-start.c:308:16

SUMMARY: AddressSanitizer: heap-use-after-free /usr/lib/gcc/x86_64-linux-gnu/10/../../../../include/c++/10/bits/unique_ptr.h:173:42 in std::__uniq_ptr_impl<sf::SoundFileReader, std::default_delete<sf::SoundFileReader> >::_M_ptr() const
Shadow bytes around the buggy address:
  0x0c1c7fff80e0: fa fa fa fa fa fa fa fa fd fd fd fd fd fd fd fd
  0x0c1c7fff80f0: fd fd fd fd fd fd fd fd fd fd fd fa fa fa fa fa
  0x0c1c7fff8100: fa fa fa fa fd fd fd fd fd fd fd fd fd fd fd fd
  0x0c1c7fff8110: fd fd fd fd fd fd fd fa fa fa fa fa fa fa fa fa
  0x0c1c7fff8120: fd fd fd fd fd fd fd fd fd fd fd fd fd fd fd fd
=>0x0c1c7fff8130: fd fd fd fa fa fa fa fa fa fa fa fa[fd]fd fd fd
  0x0c1c7fff8140: fd fd fd fd fd fd fd fd fd fd fd fd fd fd fd fa
  0x0c1c7fff8150: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0c1c7fff8160: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0c1c7fff8170: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
  0x0c1c7fff8180: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
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
  Shadow gap:              cc
==1714327==ABORTING
MS: 0 ; base unit: 0000000000000000000000000000000000000000
artifact_prefix='./'; Test unit written to ./crash-1d244f35567ef782713b8e622a0959a5edb40d18
```
The issue appears to be caused by a missing synchronization between the internal audio playback thread (created by the miniaudio library, thread T9 in the log above) and the main thread that destroys the sf::Music instance (thread T0). Specifically:

- The bug is triggered when the main thread (T0) begins destroying the sf::Music object and its base classes (Music.cpp:100).
- Simultaneously, a separate audio thread (T9), created during initialization in AudioDevice.cpp, continues to run a dataCallback function (AudioDevice.cpp:491).
- This callback eventually calls sf::Music::onGetData(), which accesses a now-deleted SoundFileReader via a dangling pointer, resulting in a heap-use-after-free.

The crash location may vary between runs due to timing differences, but the underlying cause remains consistent. sf::Music inherits from AudioResource, which owns the AudioDevice responsible for managing the ma_device thread. However, the audio thread is only shut down in AudioDevice’s destructor (AudioDevice.cpp:152), which runs after the sf::Music destructor has already destroyed the playback resources. This leaves a window where the thread can execute code accessing freed memory. On the other hand, although ~Music() does call stop() (Music.cpp:98), this only pauses the playback via ma_sound_stop() and does not guarantee that the background thread has finished processing or invoking callbacks.

To fix this, SFML should ensure full synchronization and thread termination before freeing any resources used by the callback. This could involve explicitly uninitializing or joining the ma_device thread earlier (e.g., in ~Music() or an overridden stop() function in sf::Music) to prevent it from running beyond the lifetime of the sf::Music object.


### Your Environment

- OS / distro / window manager: Ubuntu 20.04 LTS
- SFML version: on master branch (commit: b95b764314eae9be2b665aa81968bbf198cf4384)
- Compiler / toolchain: clang 14.0.0
- Special compiler / CMake flags: Address Sanitizer (-fno-omit-frame-pointer -fno-sanitize-recover=all -fsanitize=address)


### Steps to reproduce

A reproduction script is included below. Please unzip this file under the root directory of SFML, and simply run the demo_bug.sh script.
[fuzz_demo_thread.zip](https://github.com/user-attachments/files/20112761/fuzz_demo_thread.zip)

**Note on reproducibility:**
While the bug’s manifestation may vary across architectures (likely due to timing differences in thread scheduling),  the underlying issue remains valid and reproducible. For example, I was able to consistently trigger the crash on a VM with an Intel Xeon Gold 6530 CPU (128 logical cores), but not on a desktop with an i7-12700K. However, this is not a hardware-specific bug, but rather a real race condition that may or may not manifest depending on timing. 

### Expected behavior

Destruction should be thread-safe and not result in any use-after-free or undefined behaviour.

### Actual behavior

The destructor of sf::Music calls stop(), but this does not guarantee that the background audio thread has finished executing. As a result, the thread may continue running after the sf::Music object and its internal members (e.g., SoundFileReader) have already been destroyed. This leads to a heap-use-after-free when the thread attempts to access freed memory during audio processing.
