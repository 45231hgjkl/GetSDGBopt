import subprocess
import re
import httpx
import os
import time
import shutil

def run_authlite():
    """运行authlite.py并获取输出"""
    try:
        result = subprocess.run(['python', 'authlite.py'], 
                              capture_output=True, text=True, cwd='getopt')
        if result.returncode != 0:
            print(f"运行authlite.py时出错: {result.stderr}")
            return None
        
        output = result.stdout.strip()
        # 清理输出中的特殊字符
        output = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', output)  # 移除控制字符
        return output
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
    """下载文件并保存到本地"""
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
    
    try:
        with httpx.stream("GET", url, timeout=60) as response:
            if response.status_code == 200:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                start_time = time.time()
                
                with open(filepath, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed_time = time.time() - start_time
                        speed = downloaded / elapsed_time / 1024  # KB/s
                        remaining_time = (total - downloaded) / (speed * 1024) if speed > 0 else 0
                        
                        progress = (downloaded / total) * 100 if total > 0 else 0
                        print(f"\r下载进度: {progress:.2f}% | 已下载: {downloaded / 1024:.2f} KB | 速度: {speed:.2f} KB/s | 已用时间: {elapsed_time:.2f}s | 剩余时间: {remaining_time:.2f}s", end="")
                
                return filepath
            else:
                print(f"下载文件失败，状态码: {response.status_code}")
                return None
    except Exception as e:
        print(f"下载文件时发生异常: {e}")
        return None

def extract_code_from_filename(filename):
    """从opt文件名中提取代码（如从SDGB_A031_20251022113758_0.opt提取A031）"""
    pattern = r'SDGB_([A-Z0-9]{4})_.*\.opt'
    match = re.search(pattern, filename)
    if match:
        return match.group(1)
    return None

def decrypt_opt_file(opt_filepath):
    """使用fstool解密opt文件"""
    try:
        # 获取文件名
        filename = os.path.basename(opt_filepath)
        
        # 提取代码
        code = extract_code_from_filename(filename)
        if not code:
            print(f"无法从文件名 {filename} 中提取代码")
            return None
        
        
        # 确保vhd文件夹存在
        vhd_dir = os.path.join('getopt','opt', 'vhd')
        if not os.path.exists(vhd_dir):
            os.makedirs(vhd_dir)
        
        # 构建输出文件名（改为.vhd格式）
        output_filename = f"{code}.vhd"
        output_filepath = os.path.join(vhd_dir, output_filename)
        
        # 检查必要文件是否存在
        opt_bin_path = os.path.join('getopt\\opt', 'OPT.BIN')
        fstool_path = os.path.join('getopt\\opt', 'fstool.exe')
        
        if not os.path.exists(opt_bin_path):
            print(f"错误: OPT.BIN 文件不存在于 {opt_bin_path}")
            return None
        if not os.path.exists(fstool_path):
            print(f"错误: fstool.exe 文件不存在于 {fstool_path}")
            return None
        
        # 构建命令
        cmd = [
            fstool_path,
            'dec',
            'OPT.BIN',
            filename,
            output_filename
        ]
        
        
        # 在opt文件夹中执行命令
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='getopt\\opt')
        
        if result.returncode == 0:
            # 检查文件是否在vhd文件夹中生成
            if os.path.exists(output_filepath):
                return output_filepath
            else:
                # 如果文件在opt文件夹中生成，移动到vhd文件夹
                temp_output = os.path.join('getopt\\opt', output_filename)
                if os.path.exists(temp_output):
                    import shutil
                    shutil.move(temp_output, output_filepath)
                    return output_filepath
                else:
                    print(f"解密成功，但未找到输出文件")
                    return None
        else:
            print(f"解密失败，错误信息: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"执行解密时发生异常: {e}")
        return None

def extract_vhd_with_poweriso(vhd_filepath):
    """使用PowerISO提取VHD文件内容"""
    try:
        # 获取VHD文件名（不含路径和扩展名）
        vhd_filename = os.path.basename(vhd_filepath)
        code = os.path.splitext(vhd_filename)[0]  # 例如：A031
        
        # 构建目标文件夹路径（更新为opt_out目录）
        target_dir = os.path.join('opt_out', code)
        
        # 确保目标文件夹存在
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        # 使用指定的piso.exe路径（更新后的路径）
        piso_path = r"getopt\piso\piso.exe"
        
        # 检查piso.exe是否存在
        if not os.path.exists(piso_path):
            print(f"错误: PowerISO 命令行工具不存在于 {piso_path}")
            print("请确保piso.exe已安装到指定路径")
            return False
        
        cmd_tool = piso_path
        
        
        # 构建提取命令 - VHD文件需要先列出分区，然后提取
        # 首先列出VHD文件内容
        list_cmd = [
            cmd_tool,
            'list',
            vhd_filepath,
            '/',
            '-r'
        ]
        
        
        # 执行列出命令，查看分区信息
        list_result = subprocess.run(list_cmd, capture_output=True, text=True)
        
        if list_result.returncode == 0:
            
            # 提取所有内容到目标目录
            extract_cmd = [
                cmd_tool,
                'extract',
                vhd_filepath,
                '/',
                '-od',
                target_dir,
                '-r'  # 递归提取所有文件
            ]
            
            
            # 执行提取命令
            extract_result = subprocess.run(extract_cmd, capture_output=True, text=True)
            
            if extract_result.returncode == 0:
                # 检查提取的文件
                extracted_files = []
                for root, dirs, files in os.walk(target_dir):
                    for file in files:
                        extracted_files.append(os.path.join(root, file))
                
                return True
            else:
                print(f"VHD文件提取失败，错误信息: {extract_result.stderr}")
                print(f"提取命令输出: {extract_result.stdout}")
                return False
        else:
            print(f"无法列出VHD文件内容，错误信息: {list_result.stderr}")
            return False
            
    except Exception as e:
        print(f"使用PowerISO提取时发生异常: {e}")
        return False

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

    if extract_vhd_with_poweriso(decrypted_file):
        cleanup_downloaded_files()
        print("\n更新包文件已保存至opt_out")
        print("\n=== 全部任务完成！===")
    else:
        print("PowerISO提取失败，但解密已完成")

if __name__ == "__main__":
    main()