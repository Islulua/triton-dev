from pathlib import Path

SDK_ROOT = Path("/login_home")
CACHE_ROOT = Path.home() / ".cache" / "triton-dev"
# Credentials are deliberately not embedded. See docs/INTEGRATION.md.
SDK_URL = (
    "https://toolchain-jfrog.tsingmicro.xyz:443/artifactory/"
    "tx8-generic-dev/tx82/daily/sdk/"
)
SDK_PATTERN = r"^TX82_SDK_Daily_(?P<stamp>\d{4}-\d{2}-\d{2}-\d{2}-\d{2})$"
PACKAGES = ("raops", "torch_raisa", "triton")
MANAGED = (
    "ENABLE_CMODEL", "RAISA_FW_PATH", "RAISA_C_TOOLCHAIN_PATH", "RAISA_CMODEL_PATH",
    "LD_LIBRARY_PATH", "PATH", "VIRTUAL_ENV", "TRITON_CACHE_DIR",
    "TRITON_DEV_SDK", "TRITON_DEV_BASE_PATH", "PYTHONHOME", "PYTHONPATH",
)
