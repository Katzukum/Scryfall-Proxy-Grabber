"""Pinned, resumable downloads for DeckTheme's internal Windows inference engines.

Manifests verified against publisher APIs on 2026-10-02. Status is local only.
LFS object IDs are SHA-256; small Hugging Face files use Git blob SHA-1.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


@dataclass(frozen=True)
class FileAsset:
    path: str
    url: str
    size: int
    digest: str
    hash_kind: str = "sha256"


EDITOR_MODEL_FILES = (
    FileAsset('models/qwenimage21-quantized/COMFY-SOURCE.md',
        'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/cb504a4090723e43f17ad01cec0359490e2de613/README.md',
        4597, '25a1bcb8183e11f903f6c8c3921c74f2e7e48e50', 'git-sha1'),
    FileAsset('models/qwenimage21-quantized/diffusion/qwen_image_2.1_int8_convrot.safetensors',
        'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/cb504a4090723e43f17ad01cec0359490e2de613/diffusion_models/qwen_image_2.1_int8_convrot.safetensors',
        7256783064, 'cb74113cb03faecd79611b01fd7fd642f0aa60d6f0b95086abee214d75eaa57d', 'sha256'),
    FileAsset('models/qwenimage21-quantized/vae/qwen_image_2.1_vae_bf16.safetensors',
        'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/cb504a4090723e43f17ad01cec0359490e2de613/vae/qwen_image_2.1_vae_bf16.safetensors',
        675509688, 'bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9', 'sha256'),
    FileAsset('models/qwenimage21-quantized/text_encoder/Qwen3VL-8B-Instruct-Q4_K_M.gguf',
        'https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/f982a07559d4a2f6c8744d840bf6fccab30eea96/Qwen3VL-8B-Instruct-Q4_K_M.gguf',
        5027784800, '67d1659bfe71b89d50b45a4ad1a9e5b997e5bb16ce5da66a6a6167abd569e9e2', 'sha256'),
    FileAsset('models/qwenimage21-quantized/TEXT-ENCODER-SOURCE.md',
        'https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/f982a07559d4a2f6c8744d840bf6fccab30eea96/README.md',
        7851, 'bf7efc4a86c352d643bc62533c561e1c74dc81c0', 'git-sha1'),
    FileAsset('models/qwenimage21-quantized/text_encoder/mmproj-Qwen3VL-8B-Instruct-F16.gguf',
        'https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/f982a07559d4a2f6c8744d840bf6fccab30eea96/mmproj-Qwen3VL-8B-Instruct-F16.gguf',
        1159029824, 'ca524100ebf825c9a870db1c580d03879e0da0ab2541697e2458e64891cf9d38', 'sha256'),
    FileAsset('models/qwenimage21-quantized/LICENSE',
        'https://huggingface.co/Qwen/Qwen-Image-2.1/resolve/d26bb61231c349cf6b7896fa83353113880e1ba3/LICENSE',
        7831, '13ae08d5a5828f508cf0e852b1b316c0c0bbb9b3', 'git-sha1'),
    FileAsset('models/qwenimage21-quantized/QWEN-SOURCE.md',
        'https://huggingface.co/Qwen/Qwen-Image-2.1/resolve/d26bb61231c349cf6b7896fa83353113880e1ba3/README.md',
        5707, 'db44574023ab5c2df91d7c5a3e64b59e41f02657', 'git-sha1'),
)

ENHANCER_MODEL_FILES = (
    FileAsset('models/prompt-enhancer/LICENSE',
        'https://huggingface.co/mozophe/Qwen-Image-2.1-PE-MTP-GGUF/resolve/b56146a6dd48f7a7eb33a0a85ad3f55376abe449/LICENSE',
        7831, '13ae08d5a5828f508cf0e852b1b316c0c0bbb9b3', 'git-sha1'),
    FileAsset('models/prompt-enhancer/NOTICE',
        'https://huggingface.co/mozophe/Qwen-Image-2.1-PE-MTP-GGUF/resolve/b56146a6dd48f7a7eb33a0a85ad3f55376abe449/NOTICE',
        148, '1cddfd79b04dc770b8994708cfa18f4f2ba30308', 'git-sha1'),
    FileAsset('models/prompt-enhancer/README.md',
        'https://huggingface.co/mozophe/Qwen-Image-2.1-PE-MTP-GGUF/resolve/b56146a6dd48f7a7eb33a0a85ad3f55376abe449/README.md',
        13020, '5ac936a0c75399c93d2d549dc48a58b896bcf8ef', 'git-sha1'),
    FileAsset('models/prompt-enhancer/qwen3.5_9b_qwen_image_2.1_pe_i2i.mmproj.bf16.gguf',
        'https://huggingface.co/mozophe/Qwen-Image-2.1-PE-MTP-GGUF/resolve/b56146a6dd48f7a7eb33a0a85ad3f55376abe449/qwen3.5_9b_qwen_image_2.1_pe_i2i.mmproj.bf16.gguf',
        921704640, '2589e2582925db166f57ae18c9d3fe5fec617ddde72d0f095c8dbc87a71f6579', 'sha256'),
    FileAsset('models/prompt-enhancer/qwen3.5_9b_qwen_image_2.1_pe_i2i.mtp.Q4_K_M.gguf',
        'https://huggingface.co/mozophe/Qwen-Image-2.1-PE-MTP-GGUF/resolve/b56146a6dd48f7a7eb33a0a85ad3f55376abe449/qwen3.5_9b_qwen_image_2.1_pe_i2i.mtp.Q4_K_M.gguf',
        5990854496, '7219bf4f49e67b8b2696eea5287f892c30fdc91c16405bdaf6883f1240bb4041', 'sha256'),
    FileAsset("models/prompt-enhancer/system_prompt.txt",
        "https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I/resolve/72927bc08afc99b7888ceb7d7d51a12db3700bbd/system_prompt.txt",
        18344, '424fcfbe2968973c57fe67e3d629df1b0a1e1550', "git-sha1"),
)

EDITOR_ARCHIVE = FileAsset(".downloads/sd-master-3f8527a-bin-win-vulkan-x64.zip",
    'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-929-3f8527a/sd-master-3f8527a-bin-win-vulkan-x64.zip',
    30067605, '60e6850d650417409f18c2170ab5e27335db96da70cd3d1ad1e930bcffc2fd35')

EDITOR_ARCHIVE_FILES = (
    ('ggml-base.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-base.dll", "",
        681984, '735999bf82d5fb52657ba145cccac30d3128e2d688394b6968f50b71efc8a958')),
    ('ggml-cpu-alderlake.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-alderlake.dll", "",
        904192, '7ef25ea2fc8c3913f0b3dae6b25c1f316d08d30527905025c68fc3393ed86caa')),
    ('ggml-cpu-cannonlake.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-cannonlake.dll", "",
        949248, '654abb884dfd137fb62be16d4815d2bf6afcc04e267420d6056e61205e27826c')),
    ('ggml-cpu-cascadelake.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-cascadelake.dll", "",
        946176, '3057e2d40f9591139bf1126c866b449a692d0068acce722089feb30347d61416')),
    ('ggml-cpu-haswell.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-haswell.dll", "",
        905216, '8958b6f234d1d364121114f76827e1608c82d1bdbfd327d2a8769a50a83821dd')),
    ('ggml-cpu-icelake.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-icelake.dll", "",
        946176, '1af8a5d354964001c7fd41bf8233f47c5a03365d591ba1da22e5347d8b59fbb7')),
    ('ggml-cpu-sandybridge.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-sandybridge.dll", "",
        879616, '5eefd377250abf0e0046e47045aa1f4689a22293e2476101a9a40827d7c399be')),
    ('ggml-cpu-skylakex.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-skylakex.dll", "",
        949248, '3f873e265b46c74f02f7e91bd343d5089a888e726ebc4a35cae97f9607361d7d')),
    ('ggml-cpu-sse42.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-sse42.dll", "",
        866304, '6998840b42451e3e4b48d134875e9faad3733d2405e91ffe27b7e44a1784ff79')),
    ('ggml-cpu-x64.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-cpu-x64.dll", "",
        867840, '8699309c7dabbd8ae037e962ba9e8d1073ed7411449e8bcf7474716bd95704c8')),
    ('ggml-vulkan.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml-vulkan.dll", "",
        42662912, '7c24c7ff74dd408e397e0a24118b60bb8b28d76439d1e0ff3d9a5b564b36667f')),
    ('ggml.dll', FileAsset("runtimes/sdcpp-3f8527a/ggml.dll", "",
        59392, '8a2bb16f90aa1183494b045d32234deb15e0521338836cd46abbec0a377db847')),
    ('ggml.txt', FileAsset("runtimes/sdcpp-3f8527a/ggml.txt", "",
        1099, 'bcd8ec749126d45cb06737d0690295d73df4b6e7e194205bcf91190368f27285')),
    ('libsharpyuv.dll', FileAsset("runtimes/sdcpp-3f8527a/libsharpyuv.dll", "",
        24576, 'ad6ca2411a2f51f5b0571b8de54a4694d58ebc0f173a80ed502bdf5d13c90596')),
    ('libwebp.dll', FileAsset("runtimes/sdcpp-3f8527a/libwebp.dll", "",
        373248, '1b089576a9c0203c361bfe5684a8a7ced3e7dbceed1eb285294cabe7a8af58e4')),
    ('libwebpmux.dll', FileAsset("runtimes/sdcpp-3f8527a/libwebpmux.dll", "",
        41984, '714ba99dfd869d83883afcd0f4a925339162390b9920e18b74d093e9ddb60cc3')),
    ('sd-cli.exe', FileAsset("runtimes/sdcpp-3f8527a/sd-cli.exe", "",
        656384, '40e2e2703e7efca2dc3f1823ef5f48f136f8fc740567b3b8f298b74788bc93ae')),
    ('stable-diffusion.cpp.txt', FileAsset("runtimes/sdcpp-3f8527a/stable-diffusion.cpp.txt", "",
        1082, '4e76049398df734a97db46f3bd4b5cbc460cb5f6bfaf737cdc3d6fbb8ab3de27')),
    ('stable-diffusion.dll', FileAsset("runtimes/sdcpp-3f8527a/stable-diffusion.dll", "",
        35304448, '4846efaf47bf4bdac3cc63dad4163968539cd61880596e39a05663dccd8c24b6')),
    ('webm.dll', FileAsset("runtimes/sdcpp-3f8527a/webm.dll", "",
        328192, '81ea3c6bf40ecf9a5b2cf44a1a7abe14a60241d123b1a8f233c60ed0748ad824')),
)

EDITOR_RUNTIME_LICENSE = FileAsset("runtimes/sdcpp-3f8527a/LICENSE",
    'https://raw.githubusercontent.com/leejet/stable-diffusion.cpp/3f8527a46c54ecf4cb4ed6003da8e8982283c73c/LICENSE',
    1062, 'b53fa08f515cb5a6fff7b9fd8fcd0961a4b80df29d74372d25e1f9171aa042ee')

ENHANCER_ARCHIVE = FileAsset(".downloads/llama-b11337-bin-win-vulkan-x64.zip",
    'https://github.com/ggml-org/llama.cpp/releases/download/b11337/llama-b11337-bin-win-vulkan-x64.zip',
    33209297, '0b2adc26fe8d9b6eda37829672b48a9ef26fc2afeffbf00d30345953121fde84')

ENHANCER_ARCHIVE_FILES = (
    ('ggml-vulkan.dll', FileAsset("runtimes/enhancer/ggml-vulkan.dll", "",
        45306880, 'f246235eff0f2ce2e90e0655eb63e6d75bdaeb82914b1054aede9c73ab13f2f3')),
    ('llama-fit-params-impl.dll', FileAsset("runtimes/enhancer/llama-fit-params-impl.dll", "",
        43008, 'ec268780940d0f2a4994c1470f2a9a32044a33f7fe3883949a463a005ee5e145')),
    ('ggml-cpu-alderlake.dll', FileAsset("runtimes/enhancer/ggml-cpu-alderlake.dll", "",
        1431552, '731fe92da5833402361fe4d803c9501511606141deca211719b217b064c7bb32')),
    ('llama-batched-bench-impl.dll', FileAsset("runtimes/enhancer/llama-batched-bench-impl.dll", "",
        61952, '7ce591697306bcf69364d01584779672e13998e73b32060ef722738d00634b70')),
    ('libomp.dll', FileAsset("runtimes/enhancer/libomp.dll", "",
        768000, 'a12116ba72d1d6820407cf30be23da04ce79d6bb8a71a5ee71759c5a1faa6f1c')),
    ('ggml-cpu-cannonlake.dll', FileAsset("runtimes/enhancer/ggml-cpu-cannonlake.dll", "",
        1657856, '7a08cfd812099816e2db0e9e07240f7665b73480cc31d0a214b8b5ca4fd5b552')),
    ('llama-server.exe', FileAsset("runtimes/enhancer/llama-server.exe", "",
        9216, '18711bd2ad88ebc1c2c12f25a0d549f99b0973853a23175302b706a1ed2fd4f0')),
    ('ggml-cpu-zen4.dll', FileAsset("runtimes/enhancer/ggml-cpu-zen4.dll", "",
        1649664, '8bfeab4a797ce783cac1492550c60c3291f7dc9353fa4a4ccff828586e440fd4')),
    ('ggml-cpu-haswell.dll', FileAsset("runtimes/enhancer/ggml-cpu-haswell.dll", "",
        1436160, '76a22fadce45aae55f076b3614aedf666463bf12bde49cf0ac3a2356bb7a4334')),
    ('llama-common.dll', FileAsset("runtimes/enhancer/llama-common.dll", "",
        7892480, 'd42ce4b42dcb17a428d8ba42a9337dcb770eb2fbd4c035d4ecbcfef9fac4d5d4')),
    ('ggml-cpu-icelake.dll', FileAsset("runtimes/enhancer/ggml-cpu-icelake.dll", "",
        1649152, 'b237440a7f0c8ba6e2f129f1c7ba121f382656833e462fc4aff200ff8768f51b')),
    ('ggml-cpu-sapphirerapids.dll', FileAsset("runtimes/enhancer/ggml-cpu-sapphirerapids.dll", "",
        1920000, 'b892aea2f971f1273a8ce5e41ace5623f783ca7c16a64ce7745478b2d6150c5f')),
    ('llama-perplexity-impl.dll', FileAsset("runtimes/enhancer/llama-perplexity-impl.dll", "",
        197632, '6a622563ea470b14ce89e2cbb88891b33c9edc90533cda8ec73df5a460622bab')),
    ('ggml-cpu-sse42.dll', FileAsset("runtimes/enhancer/ggml-cpu-sse42.dll", "",
        916480, '893027b5278d318e461e4d31726b8cee84c5b64808df4f0624f8a489cedbd44c')),
    ('ggml-cpu-cascadelake.dll', FileAsset("runtimes/enhancer/ggml-cpu-cascadelake.dll", "",
        1642496, '381fdbd85f600be8e10786c6e0f83660c2860bca977828109fb305b0abfabe0a')),
    ('ggml-rpc.dll', FileAsset("runtimes/enhancer/ggml-rpc.dll", "",
        168448, 'd259895d0a1181cc5ac723e5284af2c58f2f4e04b45d8aa80aec75687cd7c619')),
    ('mtmd.dll', FileAsset("runtimes/enhancer/mtmd.dll", "",
        1795072, '69d47e94551c8c6406a2adc944f43576be6ce6ed4821d2636f78e01f8606b552')),
    ('ggml-base.dll', FileAsset("runtimes/enhancer/ggml-base.dll", "",
        801280, '5626c8d5b2136563e30e72246f8976ae3fd579132d3ba281ac6b6e7000c8e0a7')),
    ('LICENSE-LLVM-OpenMP', FileAsset("runtimes/enhancer/LICENSE-LLVM-OpenMP", "",
        19741, 'fdad1758a9e1f9d5a81e18879b3406772115edc92c24bfa36b70c654f325e8e4')),
    ('llama.dll', FileAsset("runtimes/enhancer/llama.dll", "",
        3270144, '2ba9cc5722fd16c8cda1506ae8f706e7aae953187c2afcb98a41a9f581bca5fb')),
    ('ggml-cpu-skylakex.dll', FileAsset("runtimes/enhancer/ggml-cpu-skylakex.dll", "",
        1651712, 'c8ce5b7d9137b8b9e098568b7c02c41a6b27e38681a6aca68d078270627da58a')),
    ('ggml-cpu-x64.dll', FileAsset("runtimes/enhancer/ggml-cpu-x64.dll", "",
        908800, '2f6335acf014a960bdb8570b859ed96e340dc4e8fbe77241635404ecf7cec71b')),
    ('llama-quantize-impl.dll', FileAsset("runtimes/enhancer/llama-quantize-impl.dll", "",
        137216, 'f40558e3eb31f4ab34b1a5e5e247e50bd606f524a11931464fd1cda8709dcff8')),
    ('ggml-cpu-cooperlake.dll', FileAsset("runtimes/enhancer/ggml-cpu-cooperlake.dll", "",
        1643520, '3defb50a019c009ba0d7d7ba35f8f3061c8d0f64c715186140b1b85d19909e7f')),
    ('llama-server-impl.dll', FileAsset("runtimes/enhancer/llama-server-impl.dll", "",
        8947200, 'f078cf23b79cdc3d9fb39f45e044577217486cccecffa58d7ef993261a36fe67')),
    ('ggml-cpu-sandybridge.dll', FileAsset("runtimes/enhancer/ggml-cpu-sandybridge.dll", "",
        1286656, 'af3feb26b8332eabcef61111cea5e64f2052e4e501d6f39ec75f4f02128ec651')),
    ('llama-cli-impl.dll', FileAsset("runtimes/enhancer/llama-cli-impl.dll", "",
        3302912, '37a4f736995d3af3d32d724e5556281496129ea4ccde3ce6af9a8750302a029d')),
    ('llama-completion-impl.dll', FileAsset("runtimes/enhancer/llama-completion-impl.dll", "",
        136192, '9e75c4919690640a830d5fdf0eba21ea12646cc87076c93a52990b455420dd50')),
    ('llama-bench-impl.dll', FileAsset("runtimes/enhancer/llama-bench-impl.dll", "",
        403968, 'e4ce621e3a983d808086e96f4e89bce9e51f169c069d2b83aa66a8b92c2741c6')),
    ('ggml.dll', FileAsset("runtimes/enhancer/ggml.dll", "",
        79872, '6619ef0fa7d2d518071499bf7205a2960f2be3591aa965b6d626a581de5c2af7')),
    ('ggml-cpu-piledriver.dll', FileAsset("runtimes/enhancer/ggml-cpu-piledriver.dll", "",
        1310208, '0ceeee30c50cad7457b420e4cde19938d2b2ea536627aa35cd40404327377d19')),
    ('ggml-cpu-ivybridge.dll', FileAsset("runtimes/enhancer/ggml-cpu-ivybridge.dll", "",
        1307136, 'f8d52ec764be9474d7bc1a8a29e6e87caab4e38f19f313bb6c5eba91117fed26')),
)

ENHANCER_RUNTIME_LICENSE = FileAsset("runtimes/enhancer/LICENSE",
    'https://raw.githubusercontent.com/ggml-org/llama.cpp/d775ebf363f777bc862a8659b6c55eec9419cf35/LICENSE',
    1078, '94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d')


# Supplemental NVIDIA engine. Portable Vulkan remains the mandatory editor runtime.
CUDA_ARCHIVES = (
    FileAsset(".downloads/cuda/sd-master-3f8527a-bin-win-cuda12-x64.zip",
        'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-929-3f8527a/sd-master-3f8527a-bin-win-cuda12-x64.zip',
        337915440, '217d6dead9abd3f827fc338268555cc179234e7e6330ef21ecb1c985e19d2dc7'),
    FileAsset(".downloads/cuda/cudart-sd-bin-win-cu12-x64.zip",
        'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-929-3f8527a/cudart-sd-bin-win-cu12-x64.zip',
        563452046, 'fe20366827d357c00797eebb58244dddab7fd9a348d70090c3871004c320f38d'),
)

CUDA_ARCHIVE_FILES = {
    ".downloads/cuda/sd-master-3f8527a-bin-win-cuda12-x64.zip": (
        ('ggml-base.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-base.dll", "",
            681984, '4f9bde06caa08d2c50ca4f2dbe9ae58a238102a8a4735bbb38370e4b86036522')),
        ('ggml-cpu-alderlake.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-alderlake.dll", "",
            904192, 'c26b3a69c891748e1088cf4ee7114a420307a3e163c568775bf6fb18f721c291')),
        ('ggml-cpu-cannonlake.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-cannonlake.dll", "",
            949248, '2f06887200bcba5a1fe32e787023229e57efd10c8c92d9496acfe92f2cc84414')),
        ('ggml-cpu-cascadelake.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-cascadelake.dll", "",
            946176, '6d061b9719ff0b0d6da8b1b635292076b980cbc35e5a34a8b003e5fb0315453d')),
        ('ggml-cpu-haswell.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-haswell.dll", "",
            905216, '6e833d63cb0f158217f42dd4d6e8ecc27ab5d5cc94c25bbe4cc7a6e7c210e149')),
        ('ggml-cpu-icelake.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-icelake.dll", "",
            946176, '8e0f4e01f82119fe66c9ef55e01cd6657bc556a79366c6c394450dcd444e4e11')),
        ('ggml-cpu-sandybridge.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-sandybridge.dll", "",
            879616, 'c81ea34af4b4f4a219b6a38e5e5294c5ebc1be4e9f135bb565aaa1bbd0e9b2a4')),
        ('ggml-cpu-skylakex.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-skylakex.dll", "",
            949248, 'e1ff22fd04b942f42b6854e34651f837d5062dac0fc47b0a1ca61837a888ef5a')),
        ('ggml-cpu-sse42.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-sse42.dll", "",
            866304, '0e3f9895fe70092b170ef87ca16b6705c1a6ae58e7c0ef6ebad0fa39a4a105ae')),
        ('ggml-cpu-x64.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cpu-x64.dll", "",
            867840, '388c28c1cb038d4a3942ea74eabaf7ec5cc855c3d1422676e509584c77218d55')),
        ('ggml-cuda.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml-cuda.dll", "",
            334327296, 'cb3b987955d53228606b226edbc83bffd8f3973d18155a68072a540a2b23ab9c')),
        ('ggml.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml.dll", "",
            59392, '49eb32a804623fa01fa457238d7d1516728e7d968205c0d5b2221d22aca1693c')),
        ('ggml.txt', FileAsset("runtimes/sdcpp-cuda-3f8527a/ggml.txt", "",
            1099, 'bcd8ec749126d45cb06737d0690295d73df4b6e7e194205bcf91190368f27285')),
        ('libsharpyuv.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/libsharpyuv.dll", "",
            24576, 'c5d9530b3999e07d4f248ca5fe9e189d1ec8e2d18876dcf6b4e7e6b63ee5148c')),
        ('libwebp.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/libwebp.dll", "",
            373248, '20e809be910d865e351fddf3438737a83a97a86aad8b0bbc5ab61b2ac33ab3e6')),
        ('libwebpmux.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/libwebpmux.dll", "",
            41984, 'dae972be6f00136ee3cecdf90c1c4298476a188366a42a8bcc4e699b224a9659')),
        ('sd-cli.exe', FileAsset("runtimes/sdcpp-cuda-3f8527a/sd-cli.exe", "",
            656384, '1d6d12fb9458813bfe0dead10725c3a7880851c4a45054ffb27c27ff670b2243')),
        ('stable-diffusion.cpp.txt', FileAsset("runtimes/sdcpp-cuda-3f8527a/stable-diffusion.cpp.txt", "",
            1082, '4e76049398df734a97db46f3bd4b5cbc460cb5f6bfaf737cdc3d6fbb8ab3de27')),
        ('stable-diffusion.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/stable-diffusion.dll", "",
            35307008, 'a2c1a8378c694f9a11dd92f5f0011cf8b458c608abbf90cd5efb153ec1699419')),
        ('webm.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/webm.dll", "",
            328192, 'b3e1fe70b9edf13e10f2f1082011cc3f219b7bd632b560079cc4e49243b20938')),
    ),
    ".downloads/cuda/cudart-sd-bin-win-cu12-x64.zip": (
        ('cublas64_12.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/cublas64_12.dll", "",
            113716224, '9513540e4ec4c51ee9e7304138c2cc255c29a8c181f9e80c38efa25738becd99')),
        ('cublasLt64_12.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/cublasLt64_12.dll", "",
            674667520, 'b199d1ff892a81b7fd3d57ba1781549609b41500b36008fef326038393ad46c7')),
        ('cudart64_12.dll', FileAsset("runtimes/sdcpp-cuda-3f8527a/cudart64_12.dll", "",
            573952, 'c2c9a9c22a9bcba90e261825968836787b331038047a26770cffb7a583c28344')),
    ),
}

CUDA_RUNTIME_LICENSES = (
    FileAsset("runtimes/sdcpp-cuda-3f8527a/LICENSE",
        'https://raw.githubusercontent.com/leejet/stable-diffusion.cpp/3f8527a46c54ecf4cb4ed6003da8e8982283c73c/LICENSE',
        1062, 'b53fa08f515cb5a6fff7b9fd8fcd0961a4b80df29d74372d25e1f9171aa042ee'),
    FileAsset("runtimes/sdcpp-cuda-3f8527a/CUDA-LICENSE.html",
        'https://docs.nvidia.com/cuda/archive/12.8.1/eula/index.html',
        103460, '6722d4c310a2ec9ad869ede3371a648fe2cfc2baaf8e1ece2c35e1dccc05752c'),
)

MODEL_FILES = {"editor": EDITOR_MODEL_FILES, "enhancer": ENHANCER_MODEL_FILES}
ARCHIVES = {"editor": EDITOR_ARCHIVE, "enhancer": ENHANCER_ARCHIVE}
ARCHIVE_FILES = {"editor": EDITOR_ARCHIVE_FILES, "enhancer": ENHANCER_ARCHIVE_FILES}
RUNTIME_LICENSES = {"editor": EDITOR_RUNTIME_LICENSE, "enhancer": ENHANCER_RUNTIME_LICENSE}
LABELS = {"editor": "Qwen Image 2.1 INT8 editor", "enhancer": "Qwen image prompt enhancer (optional)"}
ModelCancelled = InterruptedError
Progress = Callable[[int, int, str], None]
_CHUNK_SIZE = 1024 * 1024


def _check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise InterruptedError("Download cancelled. Completed files and partial downloads were kept.")


class AssetManager:
    """Manage immutable assets, keeping partial downloads reusable across app restarts.

    Only a successfully verified file receives a receipt. Status checks the receipt
    and filesystem metadata without rereading tens of gigabytes on each UI poll.
    Install also hashes unreceipted files, including files supplied in an app build.
    Callers should serialize installs with inference; a lock serializes installs here.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._install_lock = threading.RLock()
        self._receipt_lock = threading.RLock()
        self._cached_cuda_probe: tuple[bool, str] | None = None
        self._editor_cuda_enabled = False
        self._editor_cuda_failure = ""
        try:
            value = json.loads((self.root / "verified-assets.json").read_text(encoding="utf-8"))
            self._receipts = value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            self._receipts = {}

    @staticmethod
    def _supported() -> bool:
        return sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64")

    def _path(self, relative: str) -> Path:
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():
            raise ValueError("DeckTheme asset path is outside the managed directory.")
        return path

    @staticmethod
    def _validate_group(group: str) -> None:
        if group not in MODEL_FILES:
            raise ValueError("Unknown model group. Expected 'editor' or 'enhancer'.")

    @staticmethod
    def _runtime_files(group: str) -> tuple[FileAsset, ...]:
        return tuple(asset for _, asset in ARCHIVE_FILES[group]) + (RUNTIME_LICENSES[group],)

    def _all_files(self, group: str) -> tuple[FileAsset, ...]:
        return self._runtime_files(group) + MODEL_FILES[group]

    def _ready(self, asset: FileAsset) -> bool:
        try:
            path = self._path(asset.path)
            metadata = path.stat()
            with self._receipt_lock:
                receipt = self._receipts.get(asset.path, {})
                return (
                    stat.S_ISREG(metadata.st_mode)
                    and metadata.st_size == asset.size
                    and isinstance(receipt, dict)
                    and receipt.get("digest") == asset.digest
                    and receipt.get("hash_kind") == asset.hash_kind
                    and receipt.get("size") == asset.size
                    and receipt.get("mtime_ns") == metadata.st_mtime_ns
                    and receipt.get("ctime_ns") == metadata.st_ctime_ns
                )
        except (OSError, ValueError):
            return False

    def status(self) -> dict:
        supported = self._supported()
        result = {
            "directory": str(self.root),
            "platform_supported": supported,
            "message": (
                "Models run locally with the app's internal Vulkan engines. GPU memory and system RAM still matter."
                if supported else "DeckTheme's internal runtime currently supports Windows x64 only."
            ),
        }
        for group in MODEL_FILES:
            files = self._all_files(group)
            installed = [asset for asset in files if self._ready(asset)]
            result[group] = {
                "ready": supported and len(installed) == len(files),
                "installed_bytes": sum(asset.size for asset in installed),
                "total_bytes": sum(asset.size for asset in files),
                "missing_files": len(files) - len(installed),
                "label": LABELS[group],
            }
        return result

    def _record(self, asset: FileAsset) -> None:
        metadata = self._path(asset.path).stat()
        with self._receipt_lock:
            self._receipts[asset.path] = {
                "digest": asset.digest, "hash_kind": asset.hash_kind, "size": metadata.st_size,
                "mtime_ns": metadata.st_mtime_ns, "ctime_ns": metadata.st_ctime_ns,
            }
            path = self.root / "verified-assets.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(self._receipts, indent=2), encoding="utf-8")
            os.replace(temporary, path)

    @staticmethod
    def _verify(path: Path, asset: FileAsset, cancel: threading.Event) -> bool:
        _check_cancel(cancel)
        if not path.is_file() or path.stat().st_size != asset.size:
            return False
        if asset.hash_kind == "git-sha1":
            digest = hashlib.sha1(b"blob " + str(asset.size).encode("ascii") + b"\0")
        elif asset.hash_kind == "sha256":
            digest = hashlib.sha256()
        else:
            raise ValueError("Unsupported asset integrity algorithm.")
        with path.open("rb") as stream:
            while chunk := stream.read(_CHUNK_SIZE):
                _check_cancel(cancel)
                digest.update(chunk)
        _check_cancel(cancel)
        return digest.hexdigest() == asset.digest

    def _existing(self, asset: FileAsset, cancel: threading.Event) -> bool:
        if self._ready(asset):
            return True
        if self._verify(self._path(asset.path), asset, cancel):
            self._record(asset)
            return True
        return False

    @staticmethod
    def _open_url(request: urllib.request.Request):
        return urllib.request.urlopen(request, timeout=30)

    def _download(self, asset: FileAsset, cancel: threading.Event, progress: Progress) -> None:
        _check_cancel(cancel)
        if self._existing(asset, cancel):
            progress(asset.size, asset.size, Path(asset.path).name)
            return
        if not asset.url.startswith("https://"):
            raise ValueError("Model downloads require a pinned HTTPS source.")
        target = self._path(asset.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = self._path(asset.path + ".part")
        last_error = None
        for attempt in range(3):
            _check_cancel(cancel)
            try:
                offset = partial.stat().st_size if partial.is_file() else 0
                if offset > asset.size:
                    partial.unlink()
                    offset = 0
                if offset != asset.size:
                    headers = {"User-Agent": "ProxyToolBox-DeckTheme/1", "Accept-Encoding": "identity"}
                    if offset:
                        headers["Range"] = f"bytes={offset}-"
                    with self._open_url(urllib.request.Request(asset.url, headers=headers)) as response:
                        if response.status == 206:
                            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                            if not match or tuple(map(int, match.groups())) != (offset, asset.size - 1, asset.size):
                                partial.unlink(missing_ok=True)
                                raise ValueError("The download server returned an unexpected resume range.")
                        elif response.status == 200:
                            offset = 0  # Server ignored Range: restart, never append duplicate bytes.
                        else:
                            raise ValueError(f"Unexpected download response: {response.status}.")
                        encoding = response.headers.get("Content-Encoding", "identity")
                        if encoding != "identity":
                            raise ValueError("Unexpected content encoding for model download.")
                        with partial.open("ab" if offset else "wb") as stream:
                            progress(offset, asset.size, target.name)
                            while chunk := response.read(_CHUNK_SIZE):
                                _check_cancel(cancel)
                                if offset + len(chunk) > asset.size:
                                    raise ValueError("Downloaded file exceeds its verified expected size.")
                                stream.write(chunk)
                                offset += len(chunk)
                                progress(offset, asset.size, target.name)
                        if offset < asset.size:
                            raise OSError("The download ended early; the partial file was kept for resume.")
                _check_cancel(cancel)
                progress(asset.size, asset.size, f"Verifying {target.name}")
                if not self._verify(partial, asset, cancel):
                    partial.unlink(missing_ok=True)
                    raise ValueError(f"Integrity check failed for {target.name}; please retry setup.")
                os.replace(partial, target)
                self._record(asset)
                return
            except InterruptedError:
                raise
            except (OSError, ValueError, urllib.error.URLError) as error:
                last_error = error
                if attempt < 2 and cancel.wait(attempt + 1):
                    _check_cancel(cancel)
        raise RuntimeError(f"Could not download {target.name}: {last_error}") from last_error

    @staticmethod
    def _bundled_roots() -> tuple[Path, ...]:
        development = Path(__file__).resolve().parents[2] / "assets" / "deck-theme-runtimes"
        packaged = getattr(sys, "_MEIPASS", None)
        return ((Path(packaged) / "deck-theme-runtimes",) if packaged else ()) + (development,)

    def _copy_bundled(self, asset: FileAsset, cancel: threading.Event) -> bool:
        candidates = [root / asset.path for root in self._bundled_roots()]
        # Reuse checksum-verified profiling assets during development; release
        # bundles use runtimes/ and never include the benchmarks directory.
        if asset.path.startswith("runtimes/sdcpp-cuda-3f8527a/"):
            candidates.extend(root / asset.path.replace("runtimes/", "benchmarks/", 1)
                              for root in self._bundled_roots())
        for source in candidates:
            if source.resolve() == self._path(asset.path).resolve() or not source.is_file():
                continue
            if not self._verify(source, asset, cancel):
                continue
            target = self._path(asset.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = self._path(asset.path + ".part")
            with source.open("rb") as src, partial.open("wb") as dest:
                while chunk := src.read(_CHUNK_SIZE):
                    _check_cancel(cancel)
                    dest.write(chunk)
            if not self._verify(partial, asset, cancel):
                raise RuntimeError(f"Could not verify bundled runtime {target.name}.")
            os.replace(partial, target)
            self._record(asset)
            return True
        return False

    def _extract_runtime(self, group: str, cancel: threading.Event) -> None:
        self._extract_archive(ARCHIVES[group], ARCHIVE_FILES[group], cancel)

    def _extract_archive(self, archive_asset: FileAsset, files: tuple, cancel: threading.Event) -> None:
        with zipfile.ZipFile(self._path(archive_asset.path)) as archive:
            names = archive.namelist()
            for member, asset in files:
                _check_cancel(cancel)
                if names.count(member) != 1:
                    raise ValueError("Runtime archive has missing or duplicate entries.")
                info = archive.getinfo(member)
                member_path = PurePosixPath(member)
                if (
                    member_path.is_absolute() or ".." in member_path.parts or "\\" in member
                    or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) or info.file_size != asset.size
                ):
                    raise ValueError("Runtime archive contains an invalid file.")
                if self._existing(asset, cancel):
                    continue
                target = self._path(asset.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._path(asset.path + ".part")
                with archive.open(info) as source, temporary.open("wb") as dest:
                    while chunk := source.read(_CHUNK_SIZE):
                        _check_cancel(cancel)
                        dest.write(chunk)
                if not self._verify(temporary, asset, cancel):
                    temporary.unlink(missing_ok=True)
                    raise ValueError(f"Runtime integrity check failed for {target.name}.")
                os.replace(temporary, target)
                self._record(asset)

    def install_runtime(self, group: str, cancel: threading.Event, on_progress: Progress) -> None:
        """Install runtime only; also used by the release build to bundle native files."""
        self._validate_group(group)
        if not self._supported():
            raise RuntimeError("The managed runtime currently supports Windows x64 only.")
        with self._install_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            assets = self._runtime_files(group)
            total = sum(asset.size for asset in assets)
            for asset in assets:
                _check_cancel(cancel)
                if not self._existing(asset, cancel):
                    self._copy_bundled(asset, cancel)
            archive_assets = [asset for _, asset in ARCHIVE_FILES[group]]
            if not all(self._ready(asset) for asset in archive_assets):
                self._download(ARCHIVES[group], cancel, lambda done, size, name:
                               on_progress(int(done / size * total), total, f"Installing internal engine: {name}"))
                self._extract_runtime(group, cancel)
            license_asset = RUNTIME_LICENSES[group]
            self._download(license_asset, cancel, lambda done, size, name: None)
            on_progress(total, total, "Internal engine ready")

    def install(self, group: str, cancel: threading.Event, on_progress: Progress) -> None:
        self._validate_group(group)
        with self._install_lock:
            _check_cancel(cancel)
            if not self._supported():
                raise RuntimeError("The managed runtime currently supports Windows x64 only.")
            self.root.mkdir(parents=True, exist_ok=True)
            files = self._all_files(group)
            total = sum(asset.size for asset in files)
            remaining = sum(
                max(0, asset.size - (self._path(asset.path + ".part").stat().st_size
                                    if self._path(asset.path + ".part").is_file() else 0))
                for asset in files if not self._ready(asset)
            )
            if shutil.disk_usage(self.root).free < remaining + ARCHIVES[group].size:
                raise RuntimeError(f"Not enough free disk space for {LABELS[group]} ({remaining / 1e9:.1f} GB needed).")
            self.install_runtime(group, cancel, lambda done, size, name: on_progress(done, total, name))
            completed = sum(asset.size for asset in self._runtime_files(group))
            for asset in MODEL_FILES[group]:
                _check_cancel(cancel)
                self._download(asset, cancel, lambda done, size, name: on_progress(completed + done, total, name))
                completed += asset.size
            on_progress(total, total, "Models ready")

    @staticmethod
    def _cuda_files() -> tuple[FileAsset, ...]:
        return tuple(asset for files in CUDA_ARCHIVE_FILES.values() for _, asset in files) + CUDA_RUNTIME_LICENSES

    def _probe_cuda(self) -> tuple[bool, str]:
        """Inspect the installed NVIDIA driver only; no model or CUDA Toolkit needed."""
        if not self._supported():
            return False, "The NVIDIA runtime currently requires Windows x64."
        try:
            # Restrict DLL lookup to System32 instead of the workspace/current directory.
            driver = ctypes.WinDLL("nvcuda.dll", winmode=0x00000800)
            signatures = {
                "cuInit": [ctypes.c_uint],
                "cuDriverGetVersion": [ctypes.POINTER(ctypes.c_int)],
                "cuDeviceGetCount": [ctypes.POINTER(ctypes.c_int)],
                "cuDeviceGet": [ctypes.POINTER(ctypes.c_int), ctypes.c_int],
                "cuDeviceComputeCapability": [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.c_int],
            }
            for name, arguments in signatures.items():
                function = getattr(driver, name)
                function.argtypes = arguments
                function.restype = ctypes.c_int
            if driver.cuInit(0) != 0:
                return False, "The NVIDIA driver could not initialize CUDA."
            version = ctypes.c_int()
            if driver.cuDriverGetVersion(ctypes.byref(version)) != 0 or version.value < 12080:
                return False, "The NVIDIA driver does not expose CUDA 12.8 support; using Vulkan."
            count = ctypes.c_int()
            if driver.cuDeviceGetCount(ctypes.byref(count)) != 0:
                return False, "The NVIDIA driver could not enumerate CUDA devices."
            for index in range(count.value):
                device, major, minor = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
                if driver.cuDeviceGet(ctypes.byref(device), index) != 0:
                    continue
                if driver.cuDeviceComputeCapability(ctypes.byref(major), ctypes.byref(minor), device) != 0:
                    continue
                if major.value * 10 + minor.value >= 75:
                    return True, "Using the NVIDIA CUDA engine for accelerated image editing."
            return False, "No NVIDIA GPU with compute capability 7.5 or newer was detected."
        except (OSError, AttributeError):
            return False, "A compatible NVIDIA CUDA driver was not detected."

    def install_editor_cuda_runtime(self, cancel: threading.Event, on_progress: Progress) -> None:
        """Install supplemental native files only; called by the worker or optional build staging."""
        if not self._supported():
            raise RuntimeError("The NVIDIA runtime currently supports Windows x64 only.")
        with self._install_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            files = self._cuda_files()
            total = sum(asset.size for asset in files)
            if all(self._ready(asset) for asset in files):
                on_progress(total, total, "NVIDIA engine ready")
                return
            for asset in files:
                _check_cancel(cancel)
                completed = sum(item.size for item in files if self._ready(item))
                on_progress(completed, total, f"Preparing NVIDIA engine: {Path(asset.path).name}")
                if not self._existing(asset, cancel):
                    self._copy_bundled(asset, cancel)
            for archive in CUDA_ARCHIVES:
                archive_files = CUDA_ARCHIVE_FILES[archive.path]
                if all(self._ready(asset) for _, asset in archive_files):
                    continue
                completed = sum(item.size for item in files if self._ready(item))
                remaining = sum(item.size for _, item in archive_files if not self._ready(item))
                if shutil.disk_usage(self.root).free < remaining + archive.size:
                    raise RuntimeError("Not enough free disk space for the optional NVIDIA engine.")
                if not self._existing(archive, cancel):
                    self._copy_bundled(archive, cancel)
                self._download(archive, cancel, lambda done, size, name:
                               on_progress(completed + int(done / size * remaining), total,
                                           f"Downloading NVIDIA engine: {name}"))
                self._extract_archive(archive, archive_files, cancel)
            for asset in CUDA_RUNTIME_LICENSES:
                completed = sum(item.size for item in files if self._ready(item))
                self._download(asset, cancel, lambda done, size, name: on_progress(completed, total, name))
            if not all(self._ready(asset) for asset in files):
                raise RuntimeError("The NVIDIA runtime did not pass its integrity checks.")
            on_progress(total, total, "NVIDIA engine ready")

    def prepare_editor_runtime(self, device: str, cancel: threading.Event, on_progress: Progress) -> str:
        """Select acceleration inside a worker, never in status() or UI polling.

        A failed CUDA probe/install falls back to Vulkan with an explicit progress
        message. Cancellation propagates. A native CUDA startup failure must be
        reported by the caller through mark_editor_cuda_unavailable(); generation
        or out-of-memory failures must not trigger an automatic second generation.
        """
        if device not in ("auto", "cpu"):
            raise ValueError("Expected automatic or CPU execution mode.")
        _check_cancel(cancel)
        if device == "cpu":
            on_progress(0, 0, "Using CPU execution.")
            return "vulkan"
        with self._install_lock:
            if self._editor_cuda_failure:
                on_progress(0, 0, f"Using Vulkan: {self._editor_cuda_failure}")
                return "vulkan"
            if self._cached_cuda_probe is None:
                self._cached_cuda_probe = self._probe_cuda()
            available, message = self._cached_cuda_probe
            if not available:
                on_progress(0, 0, f"Using Vulkan: {message}")
                return "vulkan"
            try:
                self.install_editor_cuda_runtime(cancel, on_progress)
            except InterruptedError:
                raise
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
                self.mark_editor_cuda_unavailable(str(error))
                on_progress(0, 0, f"NVIDIA engine setup failed; using Vulkan: {error}")
                return "vulkan"
            self._editor_cuda_enabled = True
            on_progress(0, 0, message)
            return "cuda"

    def mark_editor_cuda_unavailable(self, reason: str) -> None:
        self._editor_cuda_failure = reason or "The NVIDIA engine could not start."
        self._editor_cuda_enabled = False

    def editor_executable(self, device: str = "auto") -> Path:
        directory = "sdcpp-cuda-3f8527a" if device != "cpu" and self._editor_cuda_enabled else "sdcpp-3f8527a"
        return self._path(f"runtimes/{directory}/sd-cli.exe")

    def editor_library(self, device: str = "auto") -> Path:
        return self.editor_executable(device).with_name("stable-diffusion.dll")

    def editor_model_dir(self) -> Path:
        return self._path("models/qwenimage21-quantized")

    def editor_diffusion_model(self) -> Path:
        return self._path("models/qwenimage21-quantized/diffusion/qwen_image_2.1_int8_convrot.safetensors")

    def editor_text_encoder(self) -> Path:
        return self._path("models/qwenimage21-quantized/text_encoder/Qwen3VL-8B-Instruct-Q4_K_M.gguf")

    def editor_vision_projector(self) -> Path:
        return self._path("models/qwenimage21-quantized/text_encoder/mmproj-Qwen3VL-8B-Instruct-F16.gguf")

    def editor_vae(self) -> Path:
        return self._path("models/qwenimage21-quantized/vae/qwen_image_2.1_vae_bf16.safetensors")

    def enhancer_executable(self) -> Path:
        return self._path("runtimes/enhancer/llama-server.exe")

    def enhancer_model(self) -> Path:
        return self._path("models/prompt-enhancer/qwen3.5_9b_qwen_image_2.1_pe_i2i.mtp.Q4_K_M.gguf")

    def enhancer_projector(self) -> Path:
        return self._path("models/prompt-enhancer/qwen3.5_9b_qwen_image_2.1_pe_i2i.mmproj.bf16.gguf")

    def enhancer_system_prompt(self) -> Path:
        return self._path("models/prompt-enhancer/system_prompt.txt")
