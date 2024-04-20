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

driver.get('https://prod.danawa.com/list/?cate=112753')
wait = WebDriverWait(driver, 10)

data = []

try:
    for i in range(1, 11):
        wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'prod_main_info')))
        products = driver.find_elements(By.CLASS_NAME, 'prod_main_info')
        for product in products:
            name = product.find_element(By.CLASS_NAME, 'prod_name').text
            name = re.sub(r"^\d+\s+", "", name)
            name = re.sub(r"\s*표준PC", "", name)
            name = re.sub(r"\s*이벤트", "", name)
            manufacturer = name.split()[0] if name.split() else "Unknown"

            memory_match = re.search(r'(\d+)GB', name)
            
            spec = product.find_element(By.CLASS_NAME, 'spec_list').text
            core_clock_match = re.search(r'베이스클럭: (\d+)MHz', spec)
            boost_clock_match = re.search(r'부스트클럭: (\d+)MHz', spec)
            length_match = re.search(r'가로\(길이\): (\d+)mm', spec)
            power_draw_match = re.search(r'정격파워 (\d+)W 이상', spec)
            outputs_match = re.findall(r'출력단자: ([\w\d.]+(?:, [\w\d.]+)*)', spec)
            
            price = product.find_element(By.CLASS_NAME, 'price_sect').text
            price = re.sub(r"[^\d]", "", price)
            if price:
              price = int(price)
            else:
              price = 0
            
            data.append({
                'Name': name,
                'Manufacturer': manufacturer,
                'Price': price,
                'Memory': int(memory_match.group(1)) if memory_match else None,
                'CoreClock': int(core_clock_match.group(1)) if core_clock_match else None,
                'BoostClock': int(boost_clock_match.group(1)) if boost_clock_match else None,
                'Length': int(length_match.group(1)) if length_match else None,
                'PowerDraw': int(power_draw_match.group(1)) if power_draw_match else None,
                'Outputs': ', '.join(outputs_match) if outputs_match else None
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
    components_df['Type'] = 'GPU'
    gpus_df = df[['Memory', 'CoreClock', 'BoostClock', 'Length', 'PowerDraw', 'Outputs']].copy()
    
    # print(tabulate(df, headers='keys', tablefmt='fancy_outline'))
    # print(tabulate(components_df, headers='keys', tablefmt='fancy_outline'))
    # print(tabulate(gpus_df, headers='keys', tablefmt='fancy_outline'))
    
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
                (row['Name'], row['Manufacturer'], row['Price'], row['Type'])
            )
            component_id = cursor.fetchone()[0]
            gpu_data = gpus_df.loc[_]
            cursor.execute(
                "INSERT INTO gpus (componentid, memory, coreclock, boostclock, length, powerdraw, outputs) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (component_id, gpu_data['Memory'], gpu_data['CoreClock'], gpu_data['BoostClock'], gpu_data['Length'], gpu_data['PowerDraw'], gpu_data['Outputs'])
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
