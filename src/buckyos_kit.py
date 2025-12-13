import subprocess
import platform
import os
import locale

_system_name = platform.system()

def get_execute_name(file_name: str) -> str:
    if _system_name == "Windows":
        return file_name + ".exe"
    return file_name

def ensure_executable(file_path: str):
    if _system_name == "Windows":
        return
        
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found")
    if not os.path.isfile(file_path):
        raise ValueError(f"File {file_path} is not a file")
    os.system(f"chmod +x {file_path}")

def ensure_directory_accessible(directory_path):
    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
    os.system(f"chmod 777 -R {directory_path}")
    
# Get system default encoding
def get_system_encoding():
    try:
        return locale.getpreferredencoding()
    except:
        return 'utf-8'
    
def get_user_data_dir(user_id: str) -> str:
    return os.path.join(get_buckyos_root(),"data", user_id)

def get_app_data_dir(app_id: str,owner_user_id: str) -> str:
    return os.path.join(get_buckyos_root(),"data", owner_user_id, app_id)

def get_app_cache_dir(app_id: str,owner_user_id: str) -> str:
    return os.path.join(get_buckyos_root(),"cache", owner_user_id, app_id)

def get_app_local_cache_dir(app_id: str,owner_user_id: str) -> str:
    return os.path.join(get_buckyos_root(),"tmp", owner_user_id, app_id)

def get_session_token_env_key(app_full_id: str, is_app_service: bool) -> str:
    app_id = app_full_id.upper().replace("-", "_")
    if not is_app_service:
        return f"{app_id}_SESSION_TOKEN"
    else:
        return f"{app_id}_TOKEN"
    
def get_full_appid(app_id: str, owner_user_id: str) -> str:
    return f"{owner_user_id}-{app_id}"

# TODO: process_full_path is the full path to the target process
def check_process_exists(process_full_path):
    if _system_name == "Windows":
        # Use tasklist command to check process
        if not process_full_path.endswith(".exe"):
            process_full_path = process_full_path + ".exe"
        try:
            process_name = os.path.basename(process_full_path)
            check_args = ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV"]
            output = subprocess.check_output(check_args).decode(get_system_encoding(), errors='ignore')
            # Check if output contains process name (excluding header line)
            lines = output.strip().split('\n')
            if len(lines) > 1:  # Has data rows
                return True
            return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            # If tasklist fails, try wmic (for compatibility)
            try:
                check_args = ["wmic", "process", "where", f"ExecutablePath like '%{process_full_path}%'", "get", "ProcessId", "/format:list"]
                output = subprocess.check_output(check_args).decode(get_system_encoding(), errors='ignore')
                return bool(output.strip())
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"Warning: Unable to check process existence on Windows. Both tasklist and wmic failed.")
                return False
    else:
        # pgrep with -f option can match full command line including complete path
        # If process_full_path is a process name, match directly
        # If it's a full path, use -f option for pattern matching
        check_args = ["pgrep", "-f", process_full_path]

        try:
            output = subprocess.check_output(check_args).decode()
            #print(f"check_process_exists {process_name} output: {output}")
            return bool(output.strip())  # If output is not empty, process exists
        except subprocess.CalledProcessError:
            return False

def check_port(port) -> bool:
    if port == 0:
        return True
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect(('localhost', port))
        sock.close()
        return True
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

def kill_process(name):
    killall_command = "killall"
    if _system_name == "Windows":
        killall_command = "taskkill /F /IM"

    if os.system(f"{killall_command} {get_execute_name(name)}") != 0:
        print(f"{name} not running")
    else:
        print(f"{name} killed")

def nohup_start(run_cmd, env_vars=None):
    cmd = f"nohup {run_cmd} > /dev/null 2>&1 &"
    creationflags = 0
    if _system_name == "Windows":
        cmd = f"start /min {run_cmd}"
        creationflags = subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW
    print(f"will run cmd {cmd} on system {_system_name}")
    
    # Create environment variables dictionary
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    
    subprocess.run(cmd, shell=True, creationflags=creationflags, env=env)
    # os.system(cmd)

def get_buckyos_root():
    buckyos_root = os.environ.get("BUCKYOS_ROOT")
    if buckyos_root:
        return buckyos_root

    if _system_name == "Windows":
        user_data_dir = os.environ.get("APPDATA")
        if not user_data_dir:
            user_data_dir = os.environ.get("USERPROFILE", ".")
        return os.path.join(user_data_dir, "buckyos")
    else:
        return "/opt/buckyos/"

