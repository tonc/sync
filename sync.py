import requests
from datetime import datetime
import time, os, sys, hashlib, subprocess

# 配置常量
TOKEN = os.getenv('TOKEN', '')
TIMEOUT = 30
SLEEP_TIME = 3

# 请求头配置
GITHUB_HEADERS = {
    'Accept': 'application/vnd.github.v3+json'
}

# 如果有token则添加Authorization头
if TOKEN:
    GITHUB_HEADERS['Authorization'] = f'token {TOKEN}'

BROWSER_HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
}

# 确保data目录存在
os.makedirs('./data', exist_ok=True)


class DownloadError(Exception):
    """下载异常类"""
    pass


def solve_pow_challenge(challenge):
    """
    求解 PoW 挑战
    寻找一个 nonce，使得 SHA256(challenge + ';' + nonce) 的前两个字节为 0
    """
    for nonce in range(10_000_000):  # 最多尝试 1000 万次
        msg = f"{challenge};{nonce}"
        hash_bytes = hashlib.sha256(msg.encode()).digest()

        # 检查前两个字节是否为 0 (Diff=4)
        if hash_bytes[0] == 0 and hash_bytes[1] == 0:
            return nonce

    raise DownloadError("无法在合理时间内求解 PoW 挑战")


def safe_request(url, headers=None, method='GET', timeout=TIMEOUT, json=None, stream=False):
    """安全的HTTP请求封装"""
    try:
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=timeout, stream=stream)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, timeout=timeout, json=json)
        elif method.upper() == 'DELETE':
            response = requests.delete(url, headers=headers, timeout=timeout)
        elif method.upper() == 'HEAD':
            response = requests.head(url, headers=headers, timeout=timeout)
        else:
            raise ValueError(f"不支持的HTTP方法: {method}")
        
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        raise DownloadError(f"请求超时: {url}")
    except requests.exceptions.ConnectionError:
        raise DownloadError(f"连接失败: {url}")
    except requests.exceptions.HTTPError as e:
        raise DownloadError(f"HTTP错误 {e.response.status_code}: {url}")
    except Exception as e:
        raise DownloadError(f"未知错误: {str(e)}")


def download_file(url, filename=None, headers=BROWSER_HEADERS):
    """下载文件并保存"""
    if headers is None:
        headers = GITHUB_HEADERS

    if filename is None:
        filename = url.split('/')[-1]

    filepath = f'./data/{filename}'

    # 检测是否需要使用 PoW 求解（salsa.debian.org）
    if 'salsa.debian.org' in url:
        try:
            print(f"[PoW] 检测到需要 PoW 挑战，开始求解...")

            session = requests.Session()

            # 第一次请求，获取 PoW 挑战页面
            response = session.get(url, headers=headers)

            # 从响应中提取 challenge cookie
            challenge = None
            for cookie in session.cookies:
                if cookie.name == 'pow_challenge':
                    challenge = cookie.value
                    break

            if not challenge:
                raise DownloadError("未找到 pow_challenge cookie")

            # 求解 PoW
            nonce = solve_pow_challenge(challenge)
            print(f"[PoW] 挑战求解成功，nonce = {nonce}")

            # 设置求解结果 cookie
            session.cookies.set('pow_nonce', str(nonce), path='/')

            # 使用求解结果请求文件
            headers['cookie'] = f"pow_challenge={challenge}; pow_nonce={nonce}"

            # 获取文件大小
            head_response = session.head(url, headers=headers)
            total_size = int(head_response.headers.get('content-length', 0))

            if total_size > 1024 * 1024:
                size_str = f"{total_size / 1024 / 1024:.1f} MB"
            else:
                size_str = f"{total_size} bytes"

            print(f"[PoW] 开始下载: {filename} ({size_str})")

            # 流式下载
            response = session.get(url, headers=headers, stream=True)

            downloaded = 0
            chunk_size = 8192
            last_print_time = time.time()

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 每秒打印一次进度
                        current_time = time.time()
                        if current_time - last_print_time >= 1.0:
                            progress = downloaded / total_size * 100 if total_size > 0 else 0
                            print(f"  下载进度: {downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB ({progress:.1f}%)")
                            last_print_time = current_time

            # 验证下载结果
            file_size = os.path.getsize(filepath)
            if file_size < 10 * 1024 * 1024:
                raise DownloadError(f"下载的文件太小 ({file_size} bytes)")

            print(f"[OK] 下载完成: {filename} ({file_size / 1024 / 1024:.1f} MB)")
            return filepath

        except Exception as e:
            print(f"[WARNING] PoW 下载失败: {str(e)}")
            print(f"[INFO] 回退到普通下载方式...")
            if os.path.exists(filepath) and os.path.getsize(filepath) < 10240:
                os.remove(filepath)

    # 检测是否需要使用外部工具（salsa.debian.org 有 PoW 保护）
    use_external_tool = 'salsa.debian.org' in url

    if use_external_tool:
        try:
            # 尝试使用 wget 或 curl（它们通常能更好地处理重定向和特殊服务）
            tool = None
            if sys.platform == 'win32':
                # Windows: 优先使用 curl（Windows 10+ 内置）
                try:
                    subprocess.run(['curl', '--version'], capture_output=True, check=True)
                    tool = 'curl'
                except:
                    pass
            else:
                # Linux/Mac: 优先使用 wget 或 curl
                for cmd in ['wget', 'curl']:
                    try:
                        subprocess.run([cmd, '--version'], capture_output=True, check=True)
                        tool = cmd
                        break
                    except:
                        pass

            if tool:
                print(f"[INFO] 使用 {tool} 下载: {filename}")

                if tool == 'wget':
                    cmd = ['wget', '-O', filepath, '--user-agent', headers.get('user-agent', ''), url]
                else:  # curl
                    cmd = ['curl', '-L', '-o', filepath, '-A', headers.get('user-agent', ''), url]

                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    # 验证下载的文件大小
                    file_size = os.path.getsize(filepath)
                    if file_size < 10240:  # 小于 10KB，可能是错误页面
                        with open(filepath, 'r', errors='ignore') as f:
                            content = f.read(1000)
                            if '<!DOCTYPE html>' in content or '<html' in content:
                                print(f"[WARNING] 下载可能是 HTML 错误页面，尝试回退到 requests")
                                os.remove(filepath)
                                raise DownloadError("下载的内容可能是错误页面")

                    print(f"[OK] 下载完成: {filename} ({file_size / 1024 / 1024:.1f} MB)")
                    return filepath
                else:
                    raise DownloadError(f"{tool} 执行失败: {result.stderr}")
        except Exception as e:
            print(f"[WARNING] 使用外部工具下载失败: {str(e)}，回退到 requests")

    # 使用 requests 下载
    try:
        # 获取文件大小
        response_head = safe_request(url, headers=headers, method='HEAD')
        total_size = int(response_head.headers.get('content-length', 0))

        # 格式化文件大小显示
        if total_size > 1024 * 1024 * 1024:
            size_str = f"{total_size / 1024 / 1024 / 1024:.1f} GB"
        elif total_size > 1024 * 1024:
            size_str = f"{total_size / 1024 / 1024:.1f} MB"
        elif total_size > 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size} bytes"

        print(f"[INFO] 下载中: {filename} ({size_str})")

        # 开始下载
        response = safe_request(url, headers=headers, stream=True)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"[OK] 下载完成: {filename}")
        return filepath
    except DownloadError as e:
        print(f"[ERROR] 下载失败 {filename}: {str(e)}")
        raise



def get_DockerDesktop():
    """获取DockerDesktop相关文件"""
    try:
        print("\n[DOCKER] 获取DockerDesktop...")
        url = 'https://api.github.com/repos/asxez/DockerDesktop-CN/releases/latest'
        response = safe_request(url, headers=GITHUB_HEADERS)
        data = response.json()
        tag_name = data['tag_name']
        
        # 要下载的文件列表
        files_to_download = [
            'app-Windows-x86.zip',
            'app-Mac-apple.zip',
            f'DockerDesktop-{tag_name}-Windows-x86.exe',
            f'DockerDesktop-{tag_name}-Mac-apple.dmg'
        ]
        
        for asset in data['assets']:
            if asset['name'] in files_to_download:
                download_file(asset['browser_download_url'])
        
        return True
    except Exception as e:
        print(f"[ERROR] 获取DockerDesktop失败: {str(e)}")
        return False

def get_fileterm():
    """获取fileterm相关文件"""
    try:
        print("\n[DOCKER] 获取fileterm...")
        url = 'https://api.github.com/repos/St0ff3l/fileterm/releases/latest'
        response = safe_request(url, headers=GITHUB_HEADERS)
        data = response.json()
        
        for asset in data['assets']:
            if 'windows-x64' in asset['browser_download_url']:
                download_file(asset['browser_download_url'])
        
        return True
    except Exception as e:
        print(f"[ERROR] 获取fileterm失败: {str(e)}")
        return False

def get_wsldashboard():
    """获取wsl-dashboard相关文件"""
    try:
        print("\n[DOCKER] 获取wsl-dashboard...")
        url = 'https://api.github.com/repos/owu/wsl-dashboard/releases/latest'
        response = safe_request(url, headers=GITHUB_HEADERS)
        data = response.json()
        
        for asset in data['assets']:
            if 'Setup.x64.exe' in asset['browser_download_url']:
                download_file(asset['browser_download_url'])
        
        return True
    except Exception as e:
        print(f"[ERROR] 获取wsl-dashboard失败: {str(e)}")
        return False


def get_WSL():
    """获取WSL安装包"""
    try:
        print("\n[WSL] 获取WSL...")
        url = 'https://api.github.com/repos/microsoft/WSL/releases/latest'
        response = safe_request(url, headers=GITHUB_HEADERS)
        data = response.json()
        tag_name = data['tag_name']
        
        for asset in data['assets']:
            if asset['name'] == f'wsl.{tag_name}.0.x64.msi':
                download_file(asset['browser_download_url'])
                return True
        
        print("[WARNING] 未找到WSL安装包")
        return False
    except Exception as e:
        print(f"[ERROR] 获取WSL失败: {str(e)}")
        return False


def get_WSL2():
    """获取WSL2发行版"""
    try:
        print("\n[WSL2] 获取WSL2发行版...")
        url = 'https://raw.githubusercontent.com/microsoft/WSL/refs/heads/master/distributions/DistributionInfo.json'
        response = safe_request(url, headers=BROWSER_HEADERS)
        data = response.json()
        
        # 获取Ubuntu和Debian下载链接
        ubuntu_url = data['ModernDistributions']['Ubuntu'][0]['Amd64Url']['Url']
        debian_url = data['ModernDistributions']['Debian'][0]['Amd64Url']['Url']
        ubuntu24_url = data['ModernDistributions']['Ubuntu-24.04'][0]['Amd64Url']['Url']
        ubuntu22_url = data['ModernDistributions']['Ubuntu-22.04'][0]['Amd64Url']['Url']
        
        download_file(ubuntu_url, headers=BROWSER_HEADERS)
        download_file(ubuntu24_url, headers=BROWSER_HEADERS)
        download_file(ubuntu22_url, headers=BROWSER_HEADERS)
        # 尝试下载 Debian，但由于 PoW 保护可能失败
        print("\n[WARNING] Debian 的下载链接受 PoW 保护，可能无法使用 requests 下载")
        print(f"   手动下载地址: {debian_url}")
        print("   提示: 可以在浏览器中打开链接下载")
        
        try:
            download_file(debian_url, headers=BROWSER_HEADERS)
        except DownloadError as e:
            print(f"   Debian 下载失败（预期情况）: {str(e)}")
            print("   请手动下载 Debian WSL 文件")
        
        return True
    except Exception as e:
        print(f"[ERROR] 获取WSL2失败: {str(e)}")
        return False


def get_docker():
    """获取Docker安装脚本"""
    try:
        print("\n[DOCKER] 获取Docker安装脚本...")
        url = 'https://get.docker.com'
        download_file(url, filename='docker.sh', headers=BROWSER_HEADERS)
        
        print("[OK] Docker安装脚本下载成功")
        return True
    except Exception as e:
        print(f"[ERROR] 获取Docker安装脚本失败: {str(e)}")
        return False

def get_daemon():
    """获取daemon"""
    try:
        print("\n[DOCKER] 获取daemon...")
        url = 'https://raw.githubusercontent.com/tonc/sync/refs/heads/main/daemon.json'
        download_file(url, filename='daemon.json', headers=BROWSER_HEADERS)
        
        print("[OK] daemon下载成功")
        return True
    except Exception as e:
        print(f"[ERROR] 获取daemon失败: {str(e)}")
        return False

def get_readme():
    """获取readme"""
    try:
        print("\n[DOCKER] 获取readme...")
        url = 'https://raw.githubusercontent.com/tonc/sync/refs/heads/main/README.md'
        download_file(url, filename='ReadMe.md', headers=BROWSER_HEADERS)
        
        print("[OK] ReadMe.md下载成功")
        return True
    except Exception as e:
        print(f"[ERROR] 获取ReadMe.md失败: {str(e)}")
        return False

def get_DistributionInfo():
    """获取DistributionInfo"""
    try:
        print("\n[DOCKER] 获取DistributionInfo...")
        url = 'https://raw.githubusercontent.com/microsoft/WSL/refs/heads/master/distributions/DistributionInfo.json'
        download_file(url, filename='DistributionInfo.json', headers=BROWSER_HEADERS)
        
        print("[OK] DistributionInfo.json下载成功")
        return True
    except Exception as e:
        print(f"[ERROR] 获取DistributionInfo.json失败: {str(e)}")
        return False
        
def get_tags_sorted_by_commit_time(repo_owner, repo_name):
    """获取GitHub仓库标签并按提交时间排序"""
    print(f"\n[TAGS] 获取仓库 {repo_owner}/{repo_name} 的标签...")
    
    try:
        # 获取标签列表
        tags_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/tags"
        response = safe_request(tags_url, headers=GITHUB_HEADERS)
        tags = response.json()
        print(f"📋 获取到 {len(tags)} 个标签")
        
    except DownloadError as e:
        print(f"[ERROR] {str(e)}")
        return {"error": str(e)}
    
    # 获取每个标签的提交时间
    tags_with_time = []
    
    for i, tag in enumerate(tags, 1):
        tag_name = tag['name']
        commit_url = tag['commit']['url']
        
        print(f"[SYNC] 处理标签 {i}/{len(tags)}: {tag_name}")
        
        try:
            commit_response = safe_request(commit_url, headers=GITHUB_HEADERS)
            commit_data = commit_response.json()
            
            # 提取提交时间
            commit_date_str = commit_data['commit']['author']['date']
            commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
            
            # 添加时间信息
            tag_with_time = tag.copy()
            tag_with_time['commit_date'] = commit_date.isoformat()
            tag_with_time['commit_message'] = commit_data['commit']['message']
            tag_with_time['author_name'] = commit_data['commit']['author']['name']
            
            tags_with_time.append(tag_with_time)
            print(f"[OK] {tag_name} - {commit_date.strftime('%Y-%m-%d %H:%M:%S')}")
            
        except DownloadError as e:
            print(f"[ERROR] 获取 {tag_name} 提交信息失败: {str(e)}")
            continue
        
        # 避免请求频率过高
        if i < len(tags):  # 最后一个不需要等待
            time.sleep(SLEEP_TIME)
    
    # 按提交时间排序（从新到旧）
    tags_with_time.sort(key=lambda x: x['commit_date'], reverse=True)
    
    print(f"[OK] 排序完成！共处理 {len(tags_with_time)} 个标签")
    return tags_with_time


def main():
    """主函数"""
    print("[START] Docker工具版本检查与同步工具")
    print("=" * 60)

    # 1. 获取并排序标签
    result = get_tags_sorted_by_commit_time("asxez", "DockerDesktop-CN")
    
    # 检查结果
    if isinstance(result, dict) and 'error' in result:
        print(f"[ERROR] 程序终止: {result['error']}")
        return -1
    
    if not result:
        print("[ERROR] 没有找到任何标签")
        return -1
    
    # 2. 显示排序结果
    print(f"\n[STATS] 标签排序结果（从新到旧）:")
    print("-" * 60)
    for i, tag in enumerate(result[:10], 1):  # 只显示前10个
        commit_date = datetime.fromisoformat(tag['commit_date'])
        print(f"{i:2d}. {tag['name']:20} {commit_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if len(result) > 10:
        print(f"    ... 还有 {len(result) - 10} 个标签")
    
    # 3. 检查最新版本
    latest_version = result[0]['name']
    print(f'\n[LATEST] 最新版本: {latest_version}')
    
    print("\n[SYNC] 开始执行更新流程...")
    print("=" * 60)
    
    # 下载所有文件
    success_count = 0
    total_count = 7
    
    if get_DockerDesktop():
        success_count += 1
    if get_fileterm():
        print('fileterm成功')
    if get_wsldashboard():
        print('wsldashboard成功')
    if get_WSL():
        success_count += 1
    if get_WSL2():
        success_count += 1
    if get_docker():
        success_count += 1
    if get_daemon():
        success_count += 1
    if get_readme():
        success_count += 1
    if get_DistributionInfo():
        success_count += 1
    print(f"\n[STATS] 下载统计: {success_count}/{total_count} 成功")
    
    if success_count == 7:  # 至少要有4个文件下载成功
        print("\n[OK] 文件下载完成！")
        # print("[OK] 任务执行成功：发现新版本并完成文件下载")
        
        return 0  # 平台期望成功返回0
    else:
        print("\n[WARNING] 下载文件数量不足")
        
        return -1


if __name__ == "__main__":
    try:
        exit_code = main()
        print(f"\n[END] 程序结束，退出码: {exit_code}")
        exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[STOP] 用户中断程序")
        
        exit(-1)
    except Exception as e:
        print(f"\n[CRASH] 程序异常退出: {str(e)}")
        
        exit(-1)
