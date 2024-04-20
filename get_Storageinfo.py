from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import pandas as pd
import psycopg2
from tabulate import tabulate

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
)

driver.get('https://prod.danawa.com/list/?cate=112760')
wait = WebDriverWait(driver, 10)

data = []

try:
    for i in range(1, 5):
        wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'prod_main_info')))
        products = driver.find_elements(By.CLASS_NAME, 'prod_main_info')
        for product in products:
            name = product.find_element(By.CLASS_NAME, 'prod_name').text
            name = re.sub(r"^\d+\s+", "", name)
            name = re.sub(r"\s*표준PC", "", name)
            name = re.sub(r"\s*이벤트", "", name)
            manufacturer = name.split()[0] if name.split() else "Unknown"
            
            spec = product.find_element(By.CLASS_NAME, 'spec_list').text
            type_match = re.search(r"M\.2|SATA|NVMe", spec)
            interface_match = re.search(r"PCIe\s?\d+\.\d+x\d+|SATA\s?\d+", spec)
            
            price_section = product.find_element(By.CLASS_NAME, 'prod_pricelist').text
            price_match = re.findall(r'(\d+TB|\d+GB)\s*([\d,]+)원', price_section)
            
            for capacity, price in price_match:
                if 'TB' in capacity:
                    capacity_size = int(capacity.replace('TB', ''))*1024
                else:
                    capacity_size = int(capacity.replace('GB', ''))
                
                data.append({
                    'Name': name,
                    'Manufacturer': manufacturer,
                    'Price': int(price)*capacity_size,
                    'Capacity': capacity_size,
                    'Type': type_match.group(0).strip() if type_match else "N/A",
                    'Interface': interface_match.group(0).strip() if interface_match else "N/A"
                })

        page_links = driver.find_element(By.CSS_SELECTOR, '#productListArea > div.prod_num_nav > div > div')
        pages = page_links.find_elements(By.TAG_NAME, 'a')
        if i < len(pages):
            pages[i].click()
        else:
            print("전체 페이지 탐색 완료.")
        wait.until(EC.staleness_of(pages[0]))

except Exception as e:
    print("크롤링/파싱 관련 에러:", str(e))
finally:
    driver.quit()
    df = pd.DataFrame(data)
    
    df.replace({"": pd.NA, "N/A": pd.NA}, inplace=True)
    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    components_df = df[['Name', 'Manufacturer', 'Price']].copy()
    components_df['Type'] = 'Storage'
    
    storage_df = df[['Capacity', 'Type', 'Interface']].copy()
    
    #print(tabulate(df, headers='keys', tablefmt='fancy_outline'))
    print(tabulate(df.head(10), headers='keys', tablefmt='fancy_outline'))
    print(tabulate(components_df.head(10), headers='keys', tablefmt='fancy_outline'))
    print(tabulate(storage_df.head(10), headers='keys', tablefmt='fancy_outline'))
    
    
    try:
        connection = psycopg2.connect(
            dbname='pc_builder_db',
            user='eunsu',
            password='asdf1234',
            host='localhost',
            port='5432'
        )
        cursor = connection.cursor()
    
        for _, row in components_df.iterrows():
            cursor.execute(
                "INSERT INTO components (name, manufacturer, price, type) VALUES (%s, %s, %s, %s) RETURNING componentid",
                (row['Name'], row['Manufacturer'], float(row['Price']), row['Type'])
            )
            component_id = cursor.fetchone()[0]
            storage_data = storage_df.loc[_]
            cursor.execute(
                "INSERT INTO storage (componentid, capacity, type, interface) VALUES (%s, %s, %s, %s)",
                (component_id, float(storage_data['Capacity']), storage_data['Type'], storage_data['Interface'])
            )
        connection.commit()
        print("데이터 삽입 완료")
    except Exception as e:
        print(f"DB 관련 에러: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()
            print("DB연결종료")
