import requests
from datetime import datetime
import time, os

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


def download_file(url, filename=None, headers=None):
    """下载文件并保存"""
    if headers is None:
        headers = GITHUB_HEADERS
    
    if filename is None:
        filename = url.split('/')[-1]
    
    filepath = f'./data/{filename}'
    
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
        
        print(f"📥 下载中: {filename} ({size_str})")
        
        # 开始下载
        response = safe_request(url, headers=headers, stream=True)
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"✅ 下载完成: {filename}")
        return filepath
    except DownloadError as e:
        print(f"❌ 下载失败 {filename}: {str(e)}")
        raise


def get_DockerDesktop():
    """获取DockerDesktop相关文件"""
    try:
        print("\n🐳 获取DockerDesktop...")
        url = 'https://api.github.com/repos/asxez/DockerDesktop-CN/releases/latest'
        response = safe_request(url, headers=GITHUB_HEADERS)
        data = response.json()
        tag_name = data['tag_name']
        
        # 要下载的文件列表
        files_to_download = [
            'app-Windows-x86.asar',
            'app-Windows-x86-v2beta.asar',
            f'DockerDesktop-{tag_name}-Windows-x86.exe'
        ]
        
        for asset in data['assets']:
            if asset['name'] in files_to_download:
                download_file(asset['browser_download_url'])
        
        return True
    except Exception as e:
        print(f"❌ 获取DockerDesktop失败: {str(e)}")
        return False


def get_WSL():
    """获取WSL安装包"""
    try:
        print("\n🪟 获取WSL...")
        url = 'https://api.github.com/repos/microsoft/WSL/releases/latest'
        response = safe_request(url, headers=GITHUB_HEADERS)
        data = response.json()
        tag_name = data['tag_name']
        
        for asset in data['assets']:
            if asset['name'] == f'wsl.{tag_name}.0.x64.msi':
                download_file(asset['browser_download_url'])
                return True
        
        print("⚠️ 未找到WSL安装包")
        return False
    except Exception as e:
        print(f"❌ 获取WSL失败: {str(e)}")
        return False


def get_WSL2():
    """获取WSL2发行版"""
    try:
        print("\n🐧 获取WSL2发行版...")
        url = 'https://raw.githubusercontent.com/microsoft/WSL/refs/heads/master/distributions/DistributionInfo.json'
        response = safe_request(url, headers=BROWSER_HEADERS)
        data = response.json()
        
        # 获取Ubuntu和Debian下载链接
        ubuntu_url = data['ModernDistributions']['Ubuntu'][0]['Amd64Url']['Url']
        debian_url = data['ModernDistributions']['Debian'][0]['Amd64Url']['Url']
        
        download_file(ubuntu_url, headers=BROWSER_HEADERS)
        download_file(debian_url, headers=BROWSER_HEADERS)
        return True
    except Exception as e:
        print(f"❌ 获取WSL2失败: {str(e)}")
        return False


def get_docker():
    """获取Docker安装脚本"""
    try:
        print("\n🐋 获取Docker安装脚本...")
        url = 'https://get.docker.com'
        download_file(url, filename='docker.sh', headers=BROWSER_HEADERS)
        
        print("✅ Docker安装脚本下载成功")
        return True
    except Exception as e:
        print(f"❌ 获取Docker安装脚本失败: {str(e)}")
        return False

def get_tags_sorted_by_commit_time(repo_owner, repo_name):
    """获取GitHub仓库标签并按提交时间排序"""
    print(f"\n🏷️ 获取仓库 {repo_owner}/{repo_name} 的标签...")
    
    try:
        # 获取标签列表
        tags_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/tags"
        response = safe_request(tags_url, headers=GITHUB_HEADERS)
        tags = response.json()
        print(f"📋 获取到 {len(tags)} 个标签")
        
    except DownloadError as e:
        print(f"❌ {str(e)}")
        return {"error": str(e)}
    
    # 获取每个标签的提交时间
    tags_with_time = []
    
    for i, tag in enumerate(tags, 1):
        tag_name = tag['name']
        commit_url = tag['commit']['url']
        
        print(f"🔄 处理标签 {i}/{len(tags)}: {tag_name}")
        
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
            print(f"✅ {tag_name} - {commit_date.strftime('%Y-%m-%d %H:%M:%S')}")
            
        except DownloadError as e:
            print(f"❌ 获取 {tag_name} 提交信息失败: {str(e)}")
            continue
        
        # 避免请求频率过高
        if i < len(tags):  # 最后一个不需要等待
            time.sleep(SLEEP_TIME)
    
    # 按提交时间排序（从新到旧）
    tags_with_time.sort(key=lambda x: x['commit_date'], reverse=True)
    
    print(f"✅ 排序完成！共处理 {len(tags_with_time)} 个标签")
    return tags_with_time


def main():
    """主函数"""
    print("🚀 Docker工具版本检查与同步工具")
    print("=" * 60)

    # 1. 获取并排序标签
    result = get_tags_sorted_by_commit_time("asxez", "DockerDesktop-CN")
    
    # 检查结果
    if isinstance(result, dict) and 'error' in result:
        print(f"❌ 程序终止: {result['error']}")
        return -1
    
    if not result:
        print("❌ 没有找到任何标签")
        return -1
    
    # 2. 显示排序结果
    print(f"\n📊 标签排序结果（从新到旧）:")
    print("-" * 60)
    for i, tag in enumerate(result[:10], 1):  # 只显示前10个
        commit_date = datetime.fromisoformat(tag['commit_date'])
        print(f"{i:2d}. {tag['name']:20} {commit_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if len(result) > 10:
        print(f"    ... 还有 {len(result) - 10} 个标签")
    
    # 3. 检查最新版本
    latest_version = result[0]['name']
    print(f'\n🏆 最新版本: {latest_version}')
    
    print("\n🔄 开始执行更新流程...")
    print("=" * 60)
    
    # 下载所有文件
    success_count = 0
    total_count = 4
    
    if get_DockerDesktop():
        success_count += 1
    if get_WSL():
        success_count += 1
    if get_WSL2():
        success_count += 1
    if get_docker():
        success_count += 1
    print(f"\n📊 下载统计: {success_count}/{total_count} 成功")
    
    if success_count >= 4:  # 至少要有4个文件下载成功
        print("\n✅ 文件下载完成！")
        # print("✅ 任务执行成功：发现新版本并完成文件下载")
        
        return 0  # 平台期望成功返回0
    else:
        print("\n⚠️ 下载文件数量不足")
        
        return -1


if __name__ == "__main__":
    try:
        exit_code = main()
        print(f"\n🏁 程序结束，退出码: {exit_code}")
        exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️ 用户中断程序")
        
        exit(-1)
    except Exception as e:
        print(f"\n💥 程序异常退出: {str(e)}")
        
        exit(-1)
