import os
import sys
import subprocess
import shutil
import platform
import tempfile
import imageio_ffmpeg
from PIL import Image

APP_NAME = 'ArchiveTube'

def copy_binary(source, destination):
    # Never modify an executable inode in place: an active process may use it,
    # and macOS caches code-signature pages by inode. Replace the staged copy.
    descriptor, temporary = tempfile.mkstemp(prefix='.runtime-', dir=os.path.dirname(destination))
    os.close(descriptor)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def get_project_root():
    # Since build.py is now in the 'deploy' folder, the project root is its parent directory
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def build_frontend():
    print("🚀 Building frontend (Vue.js)...")
    frontend_dir = os.path.join(get_project_root(), 'frontend')
    
    # Run npm run build
    npm_cmd = 'npm.cmd' if platform.system() == 'Windows' else 'npm'
    result = subprocess.run([npm_cmd, 'run', 'build'], cwd=frontend_dir)
    if result.returncode != 0:
        print("❌ Frontend build failed!")
        sys.exit(1)
    print("✅ Frontend build completed.\n")

def prepare_binaries():
    print("📦 Preparing bundled runtimes...")
    root_dir = get_project_root()
    bin_dir = os.path.join(root_dir, 'bin')
    os.makedirs(bin_dir, exist_ok=True)
    
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    dest_name = 'ffmpeg.exe' if platform.system() == 'Windows' else 'ffmpeg'
    dest_path = os.path.join(bin_dir, dest_name)
    
    copy_binary(ffmpeg_exe, dest_path)
    print(f"✅ Copied ffmpeg to {dest_path}")

    ffprobe_exe = shutil.which('ffprobe.exe' if platform.system() == 'Windows' else 'ffprobe')
    if not ffprobe_exe:
        raise RuntimeError('FFprobe is required. Install the FFmpeg tools and add ffprobe to PATH.')
    ffprobe_dest = os.path.join(bin_dir, 'ffprobe.exe' if platform.system() == 'Windows' else 'ffprobe')
    copy_binary(ffprobe_exe, ffprobe_dest)
    # Homebrew's ffprobe depends on shared libraries; --add-binary lets PyInstaller
    # discover, relocate and sign these dependencies for the app bundle.
    print(f"✅ Copied ffprobe to {ffprobe_dest}")

    # Recent YouTube streams require yt-dlp's EJS challenge solver. Bundle a
    # supported Node runtime so the macOS/Windows app does not depend on the
    # user's shell PATH (GUI apps normally do not inherit it).
    node_exe = shutil.which('node.exe' if platform.system() == 'Windows' else 'node')
    if not node_exe:
        print("❌ Node.js 22+ is required to build ArchiveTube.")
        sys.exit(1)
    node_name = 'node.exe' if platform.system() == 'Windows' else 'node'
    node_dest = os.path.join(bin_dir, node_name)
    copy_binary(node_exe, node_dest)
    print(f"✅ Copied Node.js to {node_dest}\n")

def prepare_icons():
    print("🎨 Preparing application icons...")
    root_dir = get_project_root()
    
    # We'll use 'icon.png' as the expected name of the uploaded image.
    # Moving it to frontend/public keeps the root directory clean.
    public_dir = os.path.join(root_dir, 'frontend', 'public')
    base_icon_path = os.path.join(public_dir, 'icon.png')
    
    if not os.path.exists(base_icon_path):
        print("⚠️ 'icon.png' not found in frontend/public directory!")
        print("Run this script again after placing your uploaded image as 'frontend/public/icon.png'.")
        sys.exit(1)

    try:
        img = Image.open(base_icon_path)
        
        # Determine target formats based on OS
        if platform.system() == 'Windows':
            icon_out = os.path.join(public_dir, 'icon.ico')
            img.save(icon_out, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
            print(f"✅ Generated {icon_out}")
            return icon_out
        elif platform.system() == 'Darwin':
            icon_out = os.path.join(public_dir, 'icon.icns')
            # Currently relying on pillow-icns or similar, or saving as PNG if external tool is needed.
            # But Pillow supports writing basic ICNS up to certain sizes.
            # We'll save it using Pillow. If it fails, we default to using a high-res PNG
            # and letting PyInstaller handle it (though macOS pyinstaller prefers .icns).
            try:
                img.save(icon_out, format='ICNS')
                print(f"✅ Generated {icon_out}")
                return icon_out
            except Exception as e:
                print(f"⚠️ Pillow ICNS save failed ({e}), falling back to png for pyinstaller...")
                return base_icon_path
        else:
            return None # Linux isn't covered in this requirement
            
    except Exception as e:
        print(f"❌ Icon generation failed: {e}")
        sys.exit(1)
        
def build_pyinstaller(icon_path):
    print("🔨 Running PyInstaller...")
    root_dir = get_project_root()
    backend_main = os.path.join(root_dir, 'backend', 'main.py')
    
    # OS specific separator for --add-data
    separator = ';' if platform.system() == 'Windows' else ':'
    
    # PyInstaller Arguments
    python_exe = os.path.join(root_dir, 'backend', 'venv', 'Scripts', 'python.exe') if platform.system() == 'Windows' else os.path.join(root_dir, 'backend', 'venv', 'bin', 'python')
    args = [
        python_exe, '-m', 'PyInstaller',
        '--noconfirm',
        '--onefile' if platform.system() == 'Windows' else '--onedir',
        '--windowed', # Same as --noconsole
        '--name', APP_NAME,
        '--distpath', os.environ.get('ARCHIVETUBE_DIST_DIR', os.path.join(root_dir, 'dist')),
        f'--add-data=frontend/dist{separator}frontend/dist',
        f'--add-binary=bin/ffmpeg{".exe" if platform.system() == "Windows" else ""}{separator}bin',
        f'--add-binary=bin/ffprobe{".exe" if platform.system() == "Windows" else ""}{separator}bin',
        f'--add-binary=bin/node{".exe" if platform.system() == "Windows" else ""}{separator}bin',
        '--collect-all', 'yt_dlp_ejs',
        '--collect-all', 'desktop_notifier',
        '--hidden-import', 'pyperclip',
        '--hidden-import', 'platformdirs',
    ]
    
    if icon_path:
        args.extend(['--icon', icon_path])

    if platform.system() == 'Darwin':
        args.extend(['--osx-bundle-identifier', 'com.archivetube.app'])
        # An explicit '-' enables hardened runtime in PyInstaller, which rejects
        # the bundled ad-hoc signed FFprobe libraries. The default already signs
        # locally without enabling library validation.
        identity = os.environ.get('ARCHIVETUBE_SIGNING_IDENTITY')
        if identity and identity != '-':
            args.extend(['--codesign-identity', identity])
            args.extend(['--osx-entitlements-file', os.path.join(root_dir, 'deploy', 'entitlements.plist')])
        
    args.append(backend_main)
    
    print(f"Running command: {' '.join(args)}")
    result = subprocess.run(args, cwd=root_dir)
    
    if result.returncode != 0:
        print("❌ PyInstaller build failed!")
        sys.exit(1)
    
    dist_file = os.path.join(
        os.environ.get('ARCHIVETUBE_DIST_DIR', os.path.join(root_dir, 'dist')),
        f'{APP_NAME}.exe' if platform.system() == 'Windows' else f'{APP_NAME}.app',
    )
    if platform.system() == 'Darwin':
        subprocess.run(['codesign', '--verify', '--deep', '--strict', dist_file], check=True)
        runtime_dir = os.path.join(dist_file, 'Contents', 'Frameworks', 'bin')
        for executable, argument in [('ffmpeg', '-version'), ('ffprobe', '-version'), ('node', '--version')]:
            result = subprocess.run([os.path.join(runtime_dir, executable), argument],
                                    check=True, capture_output=True, text=True)
            print(f'✅ Bundled runtime: {result.stdout.splitlines()[0]}')
    print(f"🎉 Build successful! Executable is at: {dist_file}")

if __name__ == '__main__':
    build_frontend()
    prepare_binaries()
    icon_path = prepare_icons()
    build_pyinstaller(icon_path)
