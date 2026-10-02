"""CFFI ABI declarations copied from the pinned stable-diffusion.cpp C header.

Source: https://raw.githubusercontent.com/leejet/stable-diffusion.cpp/3f8527a/include/stable-diffusion.h
Header SHA256: c655beb9d3c9b8d33dd5e9d71b2fe96bf17c1aaa06dcf35d893ff277a3fd13a3
Upstream is MIT licensed; its license is bundled with the native runtime.
Do not update these declarations independently of the pinned native runtime.

MIT License
Copyright (c) 2023 leejet

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from cffi import FFI

PINNED_COMMIT = "3f8527a"
CDEF = r"""
enum rng_type_t {
    STD_DEFAULT_RNG,
    CUDA_RNG,
    CPU_RNG,
    RNG_TYPE_COUNT
};

enum sample_method_t {
    EULER_SAMPLE_METHOD,
    EULER_A_SAMPLE_METHOD,
    HEUN_SAMPLE_METHOD,
    DPM2_SAMPLE_METHOD,
    DPMPP2S_A_SAMPLE_METHOD,
    DPMPP2M_SAMPLE_METHOD,
    DPMPP2Mv2_SAMPLE_METHOD,
    IPNDM_SAMPLE_METHOD,
    IPNDM_V_SAMPLE_METHOD,
    LCM_SAMPLE_METHOD,
    DDIM_TRAILING_SAMPLE_METHOD,
    TCD_SAMPLE_METHOD,
    RES_MULTISTEP_SAMPLE_METHOD,
    RES_2S_SAMPLE_METHOD,
    ER_SDE_SAMPLE_METHOD,
    EULER_CFG_PP_SAMPLE_METHOD,
    EULER_A_CFG_PP_SAMPLE_METHOD,
    EULER_GE_SAMPLE_METHOD,
    DPMPP2M_SDE_SAMPLE_METHOD,
    DPMPP2M_SDE_BT_SAMPLE_METHOD,
    LMS_SAMPLE_METHOD,
    SAMPLE_METHOD_COUNT
};


enum scheduler_t {
    DISCRETE_SCHEDULER,
    KARRAS_SCHEDULER,
    EXPONENTIAL_SCHEDULER,
    AYS_SCHEDULER,
    GITS_SCHEDULER,
    SGM_UNIFORM_SCHEDULER,
    SIMPLE_SCHEDULER,
    SMOOTHSTEP_SCHEDULER,
    KL_OPTIMAL_SCHEDULER,
    LCM_SCHEDULER,
    BONG_TANGENT_SCHEDULER,
    LTX2_SCHEDULER,
    LOGIT_NORMAL_SCHEDULER,
    FLUX2_SCHEDULER,
    FLUX_SCHEDULER,
    BETA_SCHEDULER,
    LLADA_IMAGE_SCHEDULER,
    SCHEDULER_COUNT
};


enum prediction_t {
    EPS_PRED,
    V_PRED,
    EDM_V_PRED,
    FLOW_PRED,
    FLUX_FLOW_PRED,
    SEFI_FLOW_PRED,
    MINIT2I_FLOW_PRED,
    SENSENOVA_U1_FLOW_PRED,
    PREDICTION_COUNT
};

// same as enum ggml_type
enum sd_type_t {
    SD_TYPE_F32  = 0,
    SD_TYPE_F16  = 1,
    SD_TYPE_Q4_0 = 2,
    SD_TYPE_Q4_1 = 3,
    // SD_TYPE_Q4_2 = 4, support has been removed
    // SD_TYPE_Q4_3 = 5, support has been removed
    SD_TYPE_Q5_0    = 6,
    SD_TYPE_Q5_1    = 7,
    SD_TYPE_Q8_0    = 8,
    SD_TYPE_Q8_1    = 9,
    SD_TYPE_Q2_K    = 10,
    SD_TYPE_Q3_K    = 11,
    SD_TYPE_Q4_K    = 12,
    SD_TYPE_Q5_K    = 13,
    SD_TYPE_Q6_K    = 14,
    SD_TYPE_Q8_K    = 15,
    SD_TYPE_IQ2_XXS = 16,
    SD_TYPE_IQ2_XS  = 17,
    SD_TYPE_IQ3_XXS = 18,
    SD_TYPE_IQ1_S   = 19,
    SD_TYPE_IQ4_NL  = 20,
    SD_TYPE_IQ3_S   = 21,
    SD_TYPE_IQ2_S   = 22,
    SD_TYPE_IQ4_XS  = 23,
    SD_TYPE_I8      = 24,
    SD_TYPE_I16     = 25,
    SD_TYPE_I32     = 26,
    SD_TYPE_I64     = 27,
    SD_TYPE_F64     = 28,
    SD_TYPE_IQ1_M   = 29,
    SD_TYPE_BF16    = 30,
    // SD_TYPE_Q4_0_4_4 = 31, support has been removed from gguf files
    // SD_TYPE_Q4_0_4_8 = 32,
    // SD_TYPE_Q4_0_8_8 = 33,
    SD_TYPE_TQ1_0 = 34,
    SD_TYPE_TQ2_0 = 35,
    // SD_TYPE_IQ4_NL_4_4 = 36,
    // SD_TYPE_IQ4_NL_4_8 = 37,
    // SD_TYPE_IQ4_NL_8_8 = 38,
    SD_TYPE_MXFP4   = 39,  // MXFP4 (1 block)
    SD_TYPE_NVFP4   = 40,  // NVFP4 (4 blocks, E4M3 scale)
    SD_TYPE_Q1_0    = 41,
    SD_TYPE_Q2_0    = 42,
    SD_TYPE_F8_E4M3 = 43,
    SD_TYPE_F8_E5M2 = 44,
    SD_TYPE_COUNT   = 45,
};

enum sd_log_level_t {
    SD_LOG_DEBUG,
    SD_LOG_VERBOSE,
    SD_LOG_INFO,
    SD_LOG_WARN,
    SD_LOG_ERROR
};

enum preview_t {
    PREVIEW_NONE,
    PREVIEW_PROJ,
    PREVIEW_TAE,
    PREVIEW_VAE,
    PREVIEW_COUNT
};

enum lora_apply_mode_t {
    LORA_APPLY_AUTO,
    LORA_APPLY_IMMEDIATELY,
    LORA_APPLY_AT_RUNTIME,
    LORA_APPLY_MODE_COUNT,
};

typedef struct {
    bool enabled;
    bool temporal_tiling;
    // Spatial tile dimensions in image pixels for both encode and decode; 0 uses 256.
    int tile_size_w;
    int tile_size_h;
    float target_overlap;
    // Positive values override tile_size: <= 1 is a dimension fraction, > 1 a target tile count.
    float rel_size_w;
    float rel_size_h;
    const char* extra_tiling_args;
} sd_tiling_params_t;

typedef struct {
    const char* name;
    const char* path;
} sd_embedding_t;

enum sd_vae_format_t {
    SD_VAE_FORMAT_AUTO = -1,
    SD_VAE_FORMAT_FLUX,
    SD_VAE_FORMAT_SD3,
    SD_VAE_FORMAT_FLUX2,
    SD_VAE_FORMAT_WAN,
    SD_VAE_FORMAT_COUNT,
};

typedef struct {
    const char* model_path;
    const char* clip_l_path;
    const char* clip_g_path;
    const char* clip_vision_path;
    const char* t5xxl_path;
    const char* llm_path;
    const char* llm_vision_path;
    const char* diffusion_model_path;
    const char* high_noise_diffusion_model_path;
    const char* uncond_diffusion_model_path;
    const char* embeddings_connectors_path;
    const char* vae_path;
    const char* audio_vae_path;
    const char* audio_encoder_path;
    const char* taesd_path;
    const char* control_net_path;
    const char* ip_adapter_path;
    const char* motion_module_path;
    const sd_embedding_t* embeddings;
    uint32_t embedding_count;
    const char* photo_maker_path;
    const char* pulid_weights_path;
    const char* tensor_type_rules;
    int n_threads;
    enum sd_type_t wtype;
    enum rng_type_t rng_type;
    enum rng_type_t sampler_rng_type;
    enum prediction_t prediction;
    enum lora_apply_mode_t lora_apply_mode;
    bool enable_mmap;
    bool flash_attn;
    bool diffusion_flash_attn;
    bool tae_preview_only;
    bool diffusion_conv_direct;
    bool vae_conv_direct;
    bool force_sdxl_vae_conv_scale;
    enum sd_vae_format_t vae_format;
    const char* max_vram;  // Optional per-device GiB budget for managed weights and runner buffers; 0 uses live free VRAM without an explicit budget
    bool disable_prefetch;  // Disable asynchronous next-segment weight prefetch
    bool eager_load;  // Load all params into the params backend at model-load time instead of lazily on first use
    const char* backend;
    const char* params_backend;
    const char* split_mode;  // weight distribution for multi-device modules: layer (default) or row, or per-module assignments e.g. "diffusion=row"
    bool auto_fit;
    const char* rpc_servers;
    const char* model_args;
    bool disable_segmented_compute;  // Force monolithic graph execution even when automatic graph cutting would fit memory better
    float linear_scale;              // Override linear input scaling; 0 keeps the model default
    float attn_scale;                // Override flash-attention K/V scaling; 0 keeps the model default
    const char* tokenizer;           // tokenizer.json path or main=FILE,clip-l=FILE,clip-g=FILE assignments; required for PiD and Lens
    bool sage_attn;
    int conditioning_cache_size;  // Maximum cached conditioning entries per context; 0 disables caching (default: 4)
} sd_ctx_params_t;

typedef struct {
    uint32_t sample_rate;
    uint32_t channels;
    uint64_t sample_count;
    float* data;
} sd_audio_t;

typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t channel;
    uint8_t* data;
} sd_image_t;

typedef struct {
    // Semicolon-separated target=...,key=value rules. NULL preserves defaults.
    const char* rules;
} sd_image_preprocess_params_t;

typedef struct {
    sd_image_t* frames;
    int frame_count;
    int fps;
    sd_audio_t audio;
} sd_ref_video_t;

typedef struct {
    int* layers;
    size_t layer_count;
    float layer_start;
    float layer_end;
    float scale;
} sd_slg_params_t;

typedef struct {
    float txt_cfg;
    float img_cfg;
    float distilled_guidance;
    sd_slg_params_t slg;
} sd_guidance_params_t;

typedef struct {
    sd_guidance_params_t guidance;
    enum scheduler_t scheduler;
    enum sample_method_t sample_method;
    int sample_steps;
    float eta;
    int shifted_timestep;
    float* custom_sigmas;
    int custom_sigmas_count;
    float flow_shift;
    const char* extra_sample_args;
} sd_sample_params_t;

typedef struct {
    sd_image_t* id_images;
    int id_images_count;
    const char* id_embed_path;
    float style_strength;
} sd_pm_params_t;  // photo maker

typedef struct {
    const char* id_embedding_path;
    float id_weight;
} sd_pulid_params_t;

enum sd_cache_mode_t {
    SD_CACHE_DISABLED = 0,
    SD_CACHE_EASYCACHE,
    SD_CACHE_UCACHE,
    SD_CACHE_DBCACHE,
    SD_CACHE_TAYLORSEER,
    SD_CACHE_CACHE_DIT,
    SD_CACHE_SPECTRUM,
};

typedef struct {
    enum sd_cache_mode_t mode;
    float reuse_threshold;
    float start_percent;
    float end_percent;
    float error_decay_rate;
    bool use_relative_threshold;
    bool reset_error_on_compute;
    int Fn_compute_blocks;
    int Bn_compute_blocks;
    float residual_diff_threshold;
    int max_warmup_steps;
    int max_cached_steps;
    int max_continuous_cached_steps;
    int taylorseer_n_derivatives;
    int taylorseer_skip_interval;
    const char* scm_mask;
    bool scm_policy_dynamic;
    float spectrum_w;
    int spectrum_m;
    float spectrum_lam;
    int spectrum_window_size;
    float spectrum_flex_window;
    int spectrum_warmup_steps;
    float spectrum_stop_percent;
} sd_cache_params_t;

typedef struct {
    bool is_high_noise;
    float multiplier;
    const char* path;
} sd_lora_t;

enum sd_hires_upscaler_t {
    SD_HIRES_UPSCALER_NONE,
    SD_HIRES_UPSCALER_LATENT,
    SD_HIRES_UPSCALER_LATENT_NEAREST,
    SD_HIRES_UPSCALER_LATENT_NEAREST_EXACT,
    SD_HIRES_UPSCALER_LATENT_ANTIALIASED,
    SD_HIRES_UPSCALER_LATENT_BICUBIC,
    SD_HIRES_UPSCALER_LATENT_BICUBIC_ANTIALIASED,
    SD_HIRES_UPSCALER_LANCZOS,
    SD_HIRES_UPSCALER_NEAREST,
    SD_HIRES_UPSCALER_MODEL,
    SD_HIRES_UPSCALER_COUNT,
};

typedef struct {
    bool enabled;
    enum sd_hires_upscaler_t upscaler;
    const char* model_path;
    float scale;
    int target_width;
    int target_height;
    int steps;
    float denoising_strength;
    int upscale_tile_size;
    float* custom_sigmas;
    int custom_sigmas_count;
} sd_hires_params_t;

typedef struct {
    const sd_lora_t* loras;
    uint32_t lora_count;
    const char* prompt;
    const char* negative_prompt;
    int clip_skip;
    sd_image_t init_image;
    sd_image_t* ref_images;
    int ref_images_count;
    const char* ref_image_args;
    sd_image_t mask_image;
    int width;
    int height;
    sd_sample_params_t sample_params;
    float strength;
    int64_t seed;
    int batch_count;
    sd_image_t control_image;
    float control_strength;
    sd_image_t ip_adapter_image;
    float ip_adapter_strength;
    sd_pm_params_t pm_params;
    sd_pulid_params_t pulid_params;
    sd_tiling_params_t vae_tiling_params;
    sd_cache_params_t cache;
    sd_hires_params_t hires;
    int qwen_image_layers;
    bool circular_x;
    bool circular_y;
    sd_image_preprocess_params_t image_preprocess;
} sd_img_gen_params_t;

typedef struct {
    const sd_lora_t* loras;
    uint32_t lora_count;
    const char* prompt;
    const char* negative_prompt;
    int clip_skip;
    sd_image_t init_image;
    sd_image_t end_image;
    sd_image_t* ref_images;
    int ref_images_count;
    sd_ref_video_t* ref_videos;
    int ref_videos_count;
    sd_audio_t* ref_audios;
    int ref_audios_count;
    sd_image_t* control_frames;
    int control_frames_size;
    int width;
    int height;
    sd_sample_params_t sample_params;
    sd_sample_params_t high_noise_sample_params;
    float moe_boundary;
    float strength;
    int64_t seed;
    int video_frames;
    int fps;
    float vace_strength;
    sd_tiling_params_t vae_tiling_params;
    sd_cache_params_t cache;
    sd_hires_params_t hires;
    bool circular_x;
    bool circular_y;
    sd_image_preprocess_params_t image_preprocess;
} sd_vid_gen_params_t;


typedef struct sd_ctx_t sd_ctx_t;
typedef void (*sd_log_cb_t)(enum sd_log_level_t, const char*, void*);
typedef void (*sd_progress_cb_t)(int, int, float, void*);
void sd_set_log_callback(sd_log_cb_t, void*);
void sd_set_progress_callback(sd_progress_cb_t, void*);
int32_t sd_get_num_physical_cores(void);
void sd_ctx_params_init(sd_ctx_params_t*);
sd_ctx_t* new_sd_ctx(const sd_ctx_params_t*);
void free_sd_ctx(sd_ctx_t*);
void sd_img_gen_params_init(sd_img_gen_params_t*);
bool generate_image(sd_ctx_t*, const sd_img_gen_params_t*, sd_image_t**, int*);
void free_sd_images(sd_image_t*, int);
enum sample_method_t sd_get_default_sample_method(const sd_ctx_t*);
enum scheduler_t sd_get_default_scheduler(const sd_ctx_t*, enum sample_method_t);
const char* sd_commit(void);
const char* sd_version(void);
bool sd_ctx_supports_image_generation(const sd_ctx_t*);

"""


def create_ffi():
    ffi = FFI()
    ffi.cdef(CDEF)
    if ffi.sizeof("void *") != 8:
        raise RuntimeError("DeckTheme's native image worker requires a 64-bit Python runtime.")
    return ffi
