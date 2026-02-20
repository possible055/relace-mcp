import os

from ...config.fs_policy import CLOUD_SYNC_EXCLUDED_DIRS

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".clj",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".rst",
    ".txt",
    ".sql",
    ".graphql",
    ".proto",
    ".cmake",
}

SPECIAL_FILENAMES = {
    "dockerfile",
    "makefile",
    "cmakelists.txt",
    "gemfile",
    "rakefile",
    "justfile",
    "taskfile",
    "vagrantfile",
    "procfile",
}

EXCLUDED_DIRS = CLOUD_SYNC_EXCLUDED_DIRS

SYNC_MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024

MAX_UPLOAD_WORKERS = int(os.getenv("RELACE_UPLOAD_MAX_WORKERS", "8"))
