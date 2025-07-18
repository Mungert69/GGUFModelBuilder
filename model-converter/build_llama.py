import subprocess
import os
import shutil
import sys

# Define paths
llama_cpp_dir = os.path.expanduser("~/code/models/llama.cpp")
src_dir = os.path.join(llama_cpp_dir, "src")
build_dir = os.path.join(llama_cpp_dir, "build")
bin_dir = os.path.join(build_dir, "bin")
patch_file = os.path.abspath("./fix-override.diff")
patch_file2 = os.path.abspath("./imatrix_word_boundary.patch")

# CMake configuration
cmake_command = [
    "cmake", "-B", build_dir,
    "-DGGML_BLAS=ON",
    "-DGGML_BLAS_VENDOR=OpenBLAS",
    "-DBLAS_INCLUDE_DIRS=~/code/models/OpenBLAS",
    "-DLLAMA_CURL=OFF"
]
build_command = ["cmake", "--build", build_dir, "--config", "Release", "-j"]

def run_command(command, cwd=None):
    """Execute shell command with error handling."""
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if process.returncode != 0:
        print(f"Command failed: {' '.join(command)}")
        print(process.stderr)
        raise RuntimeError(process.stderr)
    return process.stdout

def apply_patch():
    """Apply patch with proper path handling from src directory first"""
    original_dir = os.getcwd()
    try:
        os.chdir(src_dir)
        try:
            print("Attempting system patch from src directory...")
            run_command(["patch", "-p1", "-i", patch_file])
            #run_command(["patch", "-p1", "-i", patch_file2])
            return True
        except RuntimeError as e:
            print(f"System patch failed: {e}")

            try:
                print("Attempting git apply from src directory...")
                run_command(["git", "apply", "--ignore-space-change", patch_file])
                #run_command(["git", "apply", "--ignore-space-change", patch_file2]) 
                return True
            except RuntimeError as e:
                print(f"Git apply failed: {e}")

                try:
                    print("Attempting 3-way merge...")
                    run_command(["git", "apply", "-3", "--ignore-space-change", patch_file])
                    #run_command(["git", "apply", "-3", "--ignore-space-change", patch_file2])
                    return True
                except RuntimeError as e:
                    print(f"3-way merge failed: {e}")

                    if subprocess.run(["grep", "-q", "if (qs.i_ffn_down < qs.n_ffn_down/8", "llama-quant.cpp"]).returncode == 0:
                        print("\nPOSSIBLE SOLUTION:")
                        print("Target code exists but patch won't apply cleanly.")
                        print("Try regenerating the patch with:")
                        print(f"cd {llama_cpp_dir} && git diff -U10 -- src/llama-quant.cpp > {patch_file}")
                    else:
                        print("\nCRITICAL: Target code has changed upstream.")
                    return False
    finally:
        os.chdir(original_dir)

def prepare_repo():
    """Forcefully clean and update repository"""
    print("Forcefully resetting repository...")

    has_commits = subprocess.run(["git", "rev-list", "-n", "1", "--all"], 
                                 cwd=llama_cpp_dir, capture_output=True).returncode == 0

    if has_commits:
        stash_result = subprocess.run(["git", "stash", "--include-untracked", "--all"], 
                                      cwd=llama_cpp_dir, capture_output=True)
        if stash_result.returncode == 0:
            subprocess.run(["git", "stash", "drop"], cwd=llama_cpp_dir, capture_output=True)

        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=llama_cpp_dir)
    else:
        print("No commits yet - skipping stash/reset")

    subprocess.run(["git", "clean", "-fd"], cwd=llama_cpp_dir)

    if has_commits:
        print("Pulling latest changes...")
        subprocess.run(["git", "pull"], cwd=llama_cpp_dir)
    else:
        print("No commits yet - skipping pull")

def build_and_copy(apply_patch_flag=False):
    """Main build process"""
    try:
        prepare_repo()

        if apply_patch_flag:
            if not apply_patch():
                raise RuntimeError("Patch application failed")

        print("Configuring build...")
        run_command(cmake_command, cwd=llama_cpp_dir)

        print("Building...")
        run_command(build_command, cwd=llama_cpp_dir)

        print("Copying binaries...")
        if not os.path.exists(bin_dir):
            raise FileNotFoundError(f"Binary directory not found: {bin_dir}")
        for f in os.listdir(bin_dir):
            shutil.copy2(os.path.join(bin_dir, f), llama_cpp_dir)

        print("\nBuild successful!")
        return True

    except Exception as e:
        print(f"\nBuild failed: {e}")
        return False

if __name__ == "__main__":
    if not os.path.exists(llama_cpp_dir):
        print(f"Error: llama.cpp directory not found at {llama_cpp_dir}")
        sys.exit(1)

    if not os.path.exists(patch_file):
        print(f"Error: Patch file not found at {patch_file}")
        sys.exit(1)

    # Change this to True if you want the patch to be applied
    sys.exit(0 if build_and_copy(apply_patch_flag=True) else 1)
