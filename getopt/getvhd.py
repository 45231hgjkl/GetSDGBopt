import subprocess
import re
import httpx
import os
import time
import shutil
from authlite import hello

def run_authlite():
    """运行authlite.py并获取输出"""
    try:
        # 直接调用hello()获取返回值（不是stdout！之前的stdout是错误用法）
        raw_output = hello()
        
        if not raw_output:
            print("authlite返回空结果")
            return None
        
        # 清理输出中的特殊字符（保留原逻辑）
        cleaned_output = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', raw_output)  # 移除控制字符
        cleaned_output = cleaned_output.strip()  # 去除首尾空白
        return cleaned_output
    except Exception as e:
        print(f"运行authlite.py时发生异常: {e}")
        return None

def extract_url_from_output(output):
    """从输出中提取URL并清理特殊字符"""
    # 匹配类似 result=1&uri=|https://... 的格式
    pattern = r'uri=\|([^|]+)'
    match = re.search(pattern, output)
    if match:
        url = match.group(1).strip()
        # 清理URL末尾的特殊字符和控制字符
        url = re.sub(r'[^\x20-\x7E]', '', url)  # 只保留可打印的ASCII字符
        # 确保URL以.txt结尾
        if not url.endswith('.txt'):
            txt_pos = url.find('.txt')
            if txt_pos != -1:
                url = url[:txt_pos + 4]  # 包含.txt
        return url.strip()
    return None

def download_txt_file(url):
    """下载并读取txt文件内容"""
    try:
        # 从URL中提取文件名
        txt_filename = url.split('/')[-1]
        txt_filepath = os.path.join('getopt\\opt', txt_filename)
        
        # 检查txt文件是否已经存在
        if os.path.exists(txt_filepath):
            with open(txt_filepath, 'r', encoding='utf-8') as f:
                return f.read()
        response = httpx.get(url, timeout=30)
        if response.status_code == 200:
            # 保存txt文件以便下次使用
            with open(txt_filepath, 'w', encoding='utf-8') as f:
                f.write(response.text)
            return response.text
        else:
            print(f"下载txt文件失败，状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"下载txt文件时发生异常: {e}")
        return None

def extract_install_url(txt_content):
    """从txt内容中提取INSTALL1的URL"""
    pattern = r'INSTALL1=([^\s]+)'
    match = re.search(pattern, txt_content)
    if match:
        return match.group(1).strip()
    return None

def download_file(url, filename=None):
    """下载文件并保存到本地(加入threading+httpx多线程)"""
    import threading
    from typing import List, Tuple

    if not filename:
        filename = url.split('/')[-1]
    
    # 确保opt文件夹存在
    opt_dir = 'getopt\\opt'
    if not os.path.exists(opt_dir):
        os.makedirs(opt_dir)
    
    filepath = os.path.join(opt_dir, filename)
    
    # 检查文件是否已经存在
    if os.path.exists(filepath):
        print(f"文件已存在，跳过下载")
        return filepath
    
    downloaded_total = 0
    lock = threading.Lock()
    is_download_failed = False
    total_size = 0

    def get_file_info() -> Tuple[int, bool]:
        """获取文件总大小和服务器是否支持Range请求"""
        nonlocal total_size
        try:
            with httpx.Client() as client:
                response = client.head(url, timeout=60)
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                accept_ranges = response.headers.get("accept-ranges", "").lower() == "bytes"
                return total_size, accept_ranges
        except Exception as e:
            print(f"获取文件信息失败: {e}")
            return 0, False

    def download_chunk(start: int, end: int, thread_id: int):
        """线程函数：下载指定字节范围的文件块"""
        nonlocal downloaded_total, is_download_failed
        headers = {"Range": f"bytes={start}-{end}"}
        chunk_size = 4096

        try:
            with httpx.stream("GET", url, headers=headers, timeout=60) as response:
                if response.status_code not in (200, 206):
                    raise Exception(f"线程{thread_id}状态码错误: {response.status_code}")

                with open(filepath, "r+b") as f:
                    f.seek(start)
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        if is_download_failed:
                            return
                        f.write(chunk)
                        with lock:
                            downloaded_total += len(chunk)
        except Exception as e:
            print(f"\n线程{thread_id}异常: {e}")
            with lock:
                is_download_failed = True

    try:
        total_size, accept_ranges = get_file_info()
        if total_size == 0:
            print("无法获取文件大小，下载失败")
            return None
        if not accept_ranges:
            print("服务器不支持分块下载，自动切换为单线程")
            '''单线程降级'''
            with httpx.stream("GET", url, timeout=60) as response:
                if response.status_code != 200:
                    print(f"单线程下载失败，状态码: {response.status_code}")
                    return None
                downloaded = 0
                start_time = time.time()
                with open(filepath, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed_time = time.time() - start_time
                        speed = downloaded / elapsed_time / 1024
                        remaining_time = (total_size - downloaded) / (speed * 1024) if speed > 0 else 0
                        progress = (downloaded / total_size) * 100 if total_size > 0 else 0
                        print(f"\r下载进度: {progress:.2f}% | 已下载: {downloaded / 1024:.2f} KB | 速度: {speed:.2f} KB/s | 已用时间: {elapsed_time:.2f}s | 剩余时间: {remaining_time:.2f}s", end="")
                print()
                return filepath

        with open(filepath, "wb") as f:
            f.truncate(total_size)

        #分块并启动32线程
        thread_count = 32
        chunk_size_per_thread = total_size // thread_count
        threads: List[threading.Thread] = []

        for i in range(thread_count):
            start = i * chunk_size_per_thread
            end = start + chunk_size_per_thread - 1 if i != thread_count - 1 else total_size - 1
            thread = threading.Thread(target=download_chunk, args=(start, end, i + 1))
            threads.append(thread)
            thread.start()
        print(f"启动32线程下载，总文件大小: {total_size / 1024:.2f} KB")

        #实时刷新进度
        start_time = time.time()
        while True:
            if all(not t.is_alive() for t in threads):
                break
            if is_download_failed:
                for t in threads:
                    if t.is_alive():
                        t.join(timeout=0.1)
                print("\n下载失败：部分线程执行异常")
                if os.path.exists(filepath):
                    os.remove(filepath)
                return None

            elapsed_time = time.time() - start_time
            speed = downloaded_total / elapsed_time / 1024 if elapsed_time > 0 else 0
            progress = (downloaded_total / total_size) * 100 if total_size > 0 else 0
            remaining_time = (total_size - downloaded_total) / (speed * 1024) if speed > 0 else 0

            print(f"\r下载进度: {progress:.2f}% | 已下载: {downloaded_total / 1024:.2f} KB | 速度: {speed:.2f} KB/s | 已用时间: {elapsed_time:.2f}s | 剩余时间: {remaining_time:.2f}s", end="")
            time.sleep(0.1)

        #验证文件完整性
        if downloaded_total == total_size and not is_download_failed:
            print(f"\n下载完成！文件路径: {filepath}")
            return filepath
        else:
            print("\n下载失败：文件不完整")
            if os.path.exists(filepath):
                os.remove(filepath)
            return None

    except Exception as e:
        print(f"\n下载文件时发生异常: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return None

def extract_code_from_filename(filename):
    """从opt文件名中提取代码（如从SDGB_A031_20251022113758_0.opt提取A031）"""
    pattern = r'SDGB_([A-Z0-9]{4})_.*\.opt'
    match = re.search(pattern, filename)
    if match:
        return match.group(1)
    return None

def decrypt_opt_file(opt_filepath):
    """使用fsdecrypt解密"""
    try:
        # 获取核心路径信息
        opt_filepath = os.path.abspath(opt_filepath) 
        opt_dir = os.path.dirname(opt_filepath)
        opt_filename = os.path.basename(opt_filepath)
        getopt_dir = os.path.dirname(opt_dir) 
        root_dir = os.path.dirname(getopt_dir)
        code = extract_code_from_filename(opt_filename)
        
        #校验必要条件
        if not code:
            print(f"无法从文件名 {opt_filename} 中提取代码，解密终止")
            return None
        
        fsdecrypt_path = os.path.join(opt_dir, 'fsdecrypt.exe')
        if not os.path.exists(fsdecrypt_path):
            print(f"错误: fsdecrypt.exe 不存在于 {fsdecrypt_path}")
            return None
        
        #定义opt_out目录（上级目录中的opt_out：getopt/opt_out）
        opt_out_dir = os.path.join(root_dir, 'opt_out')
        if not os.path.exists(opt_out_dir):
            os.makedirs(opt_out_dir)
            print(f"创建opt_out目录：{opt_out_dir}")
        
        #构建解密命令
        cmd = [fsdecrypt_path, opt_filename]
        print(f"\n正在解密：{opt_filename}")
        
        import sys
        with subprocess.Popen(
            cmd,
            cwd=opt_dir,
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        ) as proc:
            while proc.poll() is None:
                line = proc.stdout.readline()
                if line:
                    sys.stdout.write(f"\r{line.strip()}")
                    sys.stdout.flush()
            remaining_output = proc.stdout.read()
            if remaining_output:
                print(f"\r{remaining_output.strip()}")
        
        #检查解密是否成功
        if proc.returncode != 0:
            print(f"\n解密失败！返回码：{proc.returncode}")
            return None
        

        original_output_dir = os.path.join(opt_dir, os.path.splitext(opt_filename)[0])

        if not os.path.exists(original_output_dir) or not os.listdir(original_output_dir):
            print("\n未找到预期命名的解压文件夹，尝试查找最新创建的文件夹...")
            all_dirs = [
                d for d in os.listdir(opt_dir) 
                if os.path.isdir(os.path.join(opt_dir, d)) 
                and not d.startswith('.')  # 排除隐藏文件夹
            ]
            if not all_dirs:
                print("未找到任何解压文件夹，解密失败")
                return None

            all_dirs.sort(
                key=lambda x: os.path.getctime(os.path.join(opt_dir, x)),
                reverse=True
            )
            original_output_dir = os.path.join(opt_dir, all_dirs[0])
            print(f"找到解压文件夹：{original_output_dir}")
        
        # 重命名文件夹为提取的code（如A031）
        renamed_dir = os.path.join(opt_dir, code)  # 重命名后路径：getopt/opt/A031
        if os.path.exists(renamed_dir):
            # 若目标名称已存在，先删除（避免冲突）
            shutil.rmtree(renamed_dir)
            print(f"已删除同名文件夹：{renamed_dir}")
        os.rename(original_output_dir, renamed_dir)
        print(f"\n文件夹重命名成功：{os.path.basename(original_output_dir)} → {code}")
        
        # 剪切重命名后的文件夹到上级目录的opt_out中（getopt/opt_out/A031）
        target_dir = os.path.join(opt_out_dir, code)
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
            print(f"已删除opt_out中同名文件夹：{target_dir}")
        shutil.move(renamed_dir, target_dir)
        print(f"文件夹剪切成功！目标路径：{target_dir}")
        
        return target_dir  # 返回最终文件夹路径

    except Exception as e:
        print(f"\n执行解密时发生异常：{str(e)}")
        # 清理异常残留的文件夹（避免垃圾文件）
        if code:
            temp_dirs = [
                os.path.join(opt_dir, code),
                os.path.join(opt_dir, os.path.splitext(opt_filename)[0])
            ]
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        return None


def cleanup_downloaded_files():
    """清理下载的文件，删除opt、txt和vhd文件"""
    try:
        deleted_files = []
        
        # 清理opt文件夹中的文件
        opt_dir = 'getopt\\opt'
        if os.path.exists(opt_dir):
            
            
            # 删除.txt文件
            for file in os.listdir(opt_dir):
                if file.endswith('.txt'):
                    file_path = os.path.join(opt_dir, file)
                    try:
                        os.remove(file_path)
                        deleted_files.append(file)
                    except Exception as e:
                        print(f"删除 {file} 失败: {e}")
        
        # 清理vhd文件夹中的文件
        vhd_dir = os.path.join(opt_dir, 'vhd')
        if os.path.exists(vhd_dir):
            for file in os.listdir(vhd_dir):
                if file.endswith('.vhd'):
                    file_path = os.path.join(vhd_dir, file)
                    try:
                        os.remove(file_path)
                        deleted_files.append(f"vhd/{file}")
                    except Exception as e:
                        print(f"删除 vhd/{file} 失败: {e}")
            
        return True
        
    except Exception as e:
        print(f"清理文件时发生异常: {e}")
        return False

def main():
    # 步骤1: 运行authlite.py
    output = run_authlite()
    if not output:
        print("authlite.py运行失败")
        return

    txt_url = extract_url_from_output(output)
    if not txt_url:
        print("无法提取txt文件URL")
        return

    txt_content = download_txt_file(txt_url)
    if not txt_content:
        print("txt文件下载失败")
        return

    install_url = extract_install_url(txt_content)
    if not install_url:
        print("无法提取INSTALL1 URL")
        return

    downloaded_file = download_file(install_url)
    if not downloaded_file:
        print("下载opt文件失败")
        return

    time.sleep(2)

    decrypted_file = decrypt_opt_file(downloaded_file)
    if not decrypted_file:
        print("解密失败")
        return
    else:
        print("\n更新包文件已保存至opt_out")
        print("\n=== 全部任务完成！===")

if __name__ == "__main__":
    main()