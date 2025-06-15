"""Menu Debug Script - Helps debug the menu data structure"""
import asyncio
import json
import sys
from pathlib import Path

# Add the parent directory to Python path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from loyverse_api import get_menu_items
from gpt_parser import get_menu_item_names

async def debug_menu():
    """Debug the menu data structure"""
    print("🔍 Debugging menu data structure...")
    
    try:
        # Get raw menu data
        print("\n1. Fetching menu data from Loyverse API...")
        menu_data = await get_menu_items()
        
        print(f"✅ Successfully fetched menu data")
        print(f"📊 Menu data type: {type(menu_data)}")
        print(f"📊 Menu data keys: {list(menu_data.keys()) if isinstance(menu_data, dict) else 'Not a dict'}")
        
        # Print first few characters of the raw data
        menu_str = json.dumps(menu_data, ensure_ascii=False, indent=2)
        print(f"📊 Menu data size: {len(menu_str)} characters")
        print(f"📊 First 500 characters of menu data:")
        print(menu_str[:500])
        print("..." if len(menu_str) > 500 else "")
        
        # Check items structure
        if isinstance(menu_data, dict) and "items" in menu_data:
            items = menu_data["items"]
            print(f"\n2. Analyzing items structure...")
            print(f"📊 Items type: {type(items)}")
            print(f"📊 Items count: {len(items) if isinstance(items, list) else 'Not a list'}")
            
            if isinstance(items, list) and items:
                print(f"📊 First item structure:")
                first_item = items[0]
                print(f"   Type: {type(first_item)}")
                if isinstance(first_item, dict):
                    print(f"   Keys: {list(first_item.keys())}")
                    print(f"   First item data:")
                    print(json.dumps(first_item, ensure_ascii=False, indent=4))
                else:
                    print(f"   Value: {first_item}")
        else:
            print(f"\n❌ No 'items' key found in menu data or menu_data is not a dict")
        
        # Test the get_menu_item_names function
        print(f"\n3. Testing get_menu_item_names function...")
        menu_names = get_menu_item_names(menu_data)
        print(f"📊 Extracted names count: {len(menu_names)}")
        print(f"📊 First 10 names: {menu_names[:10]}")
        
        if not menu_names:
            print("❌ No menu names extracted! Let's debug why...")
            
            # Manual extraction to debug
            if isinstance(menu_data, dict) and "items" in menu_data:
                items = menu_data["items"]
                if isinstance(items, list):
                    print(f"📊 Manually checking first few items for name field...")
                    for i, item in enumerate(items[:5]):
                        print(f"   Item {i}: {type(item)}")
                        if isinstance(item, dict):
                            if "name" in item:
                                print(f"      ✅ Has 'name': {item['name']}")
                            else:
                                print(f"      ❌ Missing 'name', keys: {list(item.keys())}")
                            
                            # Check for alternative name fields
                            for key in item.keys():
                                if 'name' in key.lower():
                                    print(f"      🔍 Alternative name field '{key}': {item[key]}")
                        else:
                            print(f"      ❌ Item is not a dict: {item}")
        
        print(f"\n4. Summary:")
        print(f"   - Menu data fetched: ✅")
        print(f"   - Items found: {len(menu_data.get('items', [])) if isinstance(menu_data, dict) else 'Unknown'}")
        print(f"   - Names extracted: {len(menu_names)}")
        
        if not menu_names:
            print("   🚨 ISSUE: No menu names were extracted!")
            print("   💡 This is why the order parsing fails.")
        
    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_menu())
