# Test a single card with DeckTheme

DeckTheme currently provides a Single Card workflow. The Deck subtab is a placeholder for future batch work.
The desktop app manages all native engines and model downloads. No external inference application or server is required.

## First run

1. Launch ProxyToolBox and open **DeckTheme → Single Card**.
2. Search for a card such as **Sol Ring** and select a printing. For a double-faced card, choose the desired face.
   Alternatively, use **Import image** to select a PNG, JPEG, or WebP from disk.
3. Enter a theme and choose **Build prompt**. This builds an editable instruction from the card metadata;
   it does not run an LLM and needs no model download.
4. Expand **Local models** and download **Qwen Image 2.1**. Keep the app open while downloading.
   Cancelling or restarting preserves partial downloads; choose Download again to resume.
5. Optionally download the **AI prompt enhancer**, then use **Enhance with AI**.
   This model sees the original card image and rewrites the instruction. Review its result before generating.
   It follows the **Processing** setting, which defaults to **Automatic · Prefer GPU**.
6. Start with **Preview · 512 × 704**, 25 steps, seed 42, and **Automatic · Prefer GPU**.
7. Choose **Generate edit**. Use the dedicated progress area to monitor or cancel the job.
8. Compare the original and result. The PNG is already saved locally; **Save image** exports another copy.
   **Use in Print Setup** selects a folder containing only the generated card image.

## Storage and memory

The editor models total approximately **14.1 GB**:

| Component | Download |
| --- | ---: |
| Qwen Image 2.1 INT8 convrot diffusion model | 7.26 GB |
| Qwen3-VL-8B Q4_K_M text encoder | 5.03 GB |
| Vision projector | 1.16 GB |
| Qwen Image 2.1 VAE | 0.68 GB |

The optional Q4 prompt enhancer plus its vision component adds approximately **6.9 GB**.
The Vulkan and prompt runtimes are bundled in release builds; source runs can acquire these internally.
On compatible NVIDIA GPUs, the app also prepares a CUDA editor runtime automatically on first generation.
Its one-time download is about **900 MB** and its installed files occupy about **1.2 GB**. No CUDA Toolkit is required.
Setup reports exact installed/download sizes and checks free disk space. Files are pinned to specific upstream versions,
verified before use, and stored under `%LOCALAPPDATA%/ProxyToolBox/deck-theme`.

These file sizes are **not VRAM usage**. Quantization reduces weight storage; reference images, activations, caches,
and decoding also need memory. **Automatic · Prefer GPU** lets both native engines use available GPU memory and
adjust model placement to fit. The prompt enhancer fits its model layers and vision projector automatically.
Image editing prefers CUDA on compatible NVIDIA hardware and uses Vulkan otherwise, with native automatic fitting
for all stages, including text encoding, plus flash attention;
VAE tiling is enabled when the runtime needs it for memory, rather than on every GPU run.

Selecting **CPU · Slow fallback** keeps both enhancement and editing on CPU. CPU image editing uses tiled VAE
processing and can be slow. Only one DeckTheme job runs at a time. The editor retains its models in a hidden native
worker for repeat generations. It unloads after five idle minutes, on cancellation or application exit, before prompt
enhancement or model downloads, and when **Release model memory** is pressed. The prompt enhancer unloads after use.
The worker uses private process pipes; it does not expose an image-generation HTTP server.

The initial package supports **Windows x64**. Vulkan support depends on GPU hardware and drivers. Other operating
systems require separately built and validated runtime packages. Minimum VRAM has not been established.
Earlier 2–4 GB estimates for the ncnn engine do not establish requirements
for this quantized stable-diffusion.cpp backend. Start with the preview preset and measure on the target hardware.

## Measured performance

On the development RTX 4090 (24 GB), using the INT8 model, an imported Sol Ring reference,
512 × 704 output, Euler sampling, and 25 steps:

| Operation | Measured elapsed time |
| --- | ---: |
| Earlier saved generation jobs | 182–306 seconds |
| Updated CUDA editor, first generation including model loading | 39.3 seconds |
| Next generation with the editor retained | 10.8 seconds |
| Retained editor with a changed prompt | 11.1 seconds |
| GPU prompt enhancement, after the initial cache warmup | 22.9 seconds |

These are local measurements, not guarantees for other hardware or resolutions. Downloads are excluded,
and the operating system's file cache was already warm. The first edit after unloading must load the models
again. The app now uses GPU text processing in Automatic mode; previously both prompt enhancement and
the image model's text encoder were explicitly placed on CPU. Retaining the editor also avoids repeated
weight loading. Benchmark images were checked for valid output.

The packaged Vulkan backend also passed image generation and shutdown checks. Its initial runs had substantial
warmup costs; once warm, a two-step compatibility edit took 38.3 seconds including startup and 6.6 seconds with
the editor retained. Those two-step checks are not directly comparable with the 25-step CUDA measurements above.

## What this preview does

- Edits the **full card**. Prompt instructions request preservation of card text, but image generation can alter
  names, rules, numbers, and symbols. Inspect them before printing. There is no artwork mask/compositing mode yet.
- Uses reduced reference dimensions and two bounded output presets to start memory testing conservatively.
- Keeps original images in `cards/`, generated images and `generation.json` provenance in `outputs/`,
  and job records in `jobs/` under the managed data folder. Prompts, seeds, settings, and card metadata are retained.
  Inference jobs also keep bounded, timestamped native logs beside their job records for performance diagnosis.
- Keeps the current card/prompt while switching tabs. After an application restart, the most recent job status and
  completed output can be recovered, but source selection and input controls are not restored.
- Supports cancellation during downloads and inference. Active inference is stopped on application exit and is
  not resumed automatically. Completed downloads remain available.
- Does not require the prompt enhancer to generate: an editable manual/template instruction is sufficient.

## Model and runtime sources

- Image engine: [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp), release `master-929-3f8527a`.
- INT8 image weights and VAE: [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1).
  These are model files; ComfyUI is not installed or used.
- Required text/vision encoder: [Qwen3-VL-8B-Instruct GGUF](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF).
- The engine's [Qwen Image 2.1 instructions](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/qwen_image_2.1.md)
  document this INT8 diffusion and GGUF encoder combination for image editing.
- Prompt engine: [llama.cpp](https://github.com/ggml-org/llama.cpp), release `b11337`.
- Prompt model: [Qwen PE-I2I GGUF conversion](https://huggingface.co/mozophe/Qwen-Image-2.1-PE-MTP-GGUF),
  with the official [Qwen PE-I2I system prompt](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I).

The Qwen model weights use the **Qwen Research License**, which limits the granted use to noncommercial
research/evaluation; commercial use needs a separate license. Model licenses and provenance notices download with
the weights. Runtime licenses ship with the internal executables.

## Developer checks

Run `python -m pytest` from the project root and `npm run build` from `frontend/`.
Inference tests use controlled native-process/HTTP substitutes and validate argument handling, cancellation,
job isolation, output integrity, face metadata, and failed jobs. They do not substitute for GPU/model benchmarks.

`python scripts/prepare_deck_theme_runtimes.py` stages native engines into
`assets/deck-theme-runtimes/runtimes` without downloading model weights. The release build runs this step automatically
and bundles only runtime files, not archive caches. An offline release build can reuse an already verified staging folder.
