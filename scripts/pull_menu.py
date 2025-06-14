"""命令行脚本：拉取并缓存菜单"""
import asyncio
from loyverse_api import get_menu_items

async def main():
    data = await get_menu_items()
    print(f"已缓存菜单，共 {len(data.get('items', []))} 项目")

if __name__ == "__main__":
    asyncio.run(main())
