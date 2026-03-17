# Large repos (>=100MB) excluded by default to avoid slow cloning
EXCLUDED_REPOS: frozenset[str] = frozenset(
    {
        # >1GB
        "langflow-ai/langflow",  # 1.2G
        # >500MB
        "PaddlePaddle/PaddleOCR",  # 645M
        "odoo/odoo",  # 603M
        # >300MB
        "ansible/ansible",  # 437M
        "pytorch/pytorch",  # 383M
        "deepfakes/faceswap",  # 374M
        "huggingface/transformers",  # 339M
        "python/cpython",  # 329M
        "All-Hands-AI/OpenHands",  # 310M
        # >100MB
        "hacksider/Deep-Live-Cam",  # 153M
        "yt-dlp/yt-dlp",  # 129M
        "pandas-dev/pandas",  # 114M
        # Previously excluded (not in current dataset)
        "home-assistant/core",
        "kubernetes/kubernetes",
        "torvalds/linux",
        "chromium/chromium",
    }
)
