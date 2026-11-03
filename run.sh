#!/bin/zsh
# Wrapper: puts this project's local toolchain on PATH, then runs the host's build script.
#
#   .tools/uv          uv (Python 3.12 lives in .venv)
#   .venv              lz4, capstone 5.x, fonttools, nsz, backports.zstd
#   .tools/dotnet      .NET SDK 10 (the extractor and the shader translator run on it)
#   .tools/xcodegen    XcodeGen (the iOS project generator)
#   .tools/glslang/bin glslangValidator
#   .tools/bin/zstd    zstd
#
# Copied from the Cross Rays workspace, where all of it was verified. Nothing is installed system-wide.
#
# Usage: ./run.sh Game [options]        e.g. ./run.sh Game --platform mac
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
export DOTNET_ROOT="$ROOT/.tools/dotnet"
export PATH="$ROOT/.tools/uv:$ROOT/.tools/dotnet:$ROOT/.tools/xcodegen/bin:$ROOT/.tools/glslang/bin:$ROOT/.tools/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
exec "$ROOT/.venv/bin/python" "$ROOT/nxnative/scripts/build_ipa_from_nsp.py" "$@"
