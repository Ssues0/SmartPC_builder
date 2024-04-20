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

driver.get('https://prod.danawa.com/list/?cate=112747')
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
            
            spec = product.find_element(By.CLASS_NAME, 'spec_list').text
            cores = re.search(r"(\d+)코어", spec)
            threads = re.search(r"(\d+)스레드", spec)
            base_clock = re.search(r"기본 클럭: (\d+\.\d+)GHz", spec)
            boost_clock = re.search(r"최대 클럭: (\d+\.\d+)GHz", spec)
            #tdp = re.search(r"TDP: ([\d~]+)W", spec)
            tdp = re.search(r'(\d+)(?:-(\d+))?W', spec)
            
            socket_search = re.search(r"(AMD|인텔)\(소켓[^)]+\)", spec)
            socket_type = socket_search.group(0) if socket_search else "N/A"
            
            price = product.find_element(By.CLASS_NAME, 'price_sect').text
            #price = re.sub(r" 가격정보 더보기", "", price)
            price = re.sub(r"[^\d]", "", price)
            if price:
              price = int(price)
            else:
              price = 0
            
            data.append({
                'Name': name,
                'Manufacturer': "AMD" if "AMD" in name else "Intel",
                'Price': price,
                'CoreCount': cores.group(1) if cores else "N/A",
                'ThreadCount': threads.group(1) if threads else "N/A",
                'BaseClock': base_clock.group(1) if base_clock else "N/A",
                'BoostClock': boost_clock.group(1) if boost_clock else "N/A",
                'TDP': tdp.group(1) if tdp else "N/A",
                'Socket': socket_type
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
    components_df['Type'] = 'CPU'
    
    cpus_df = df[['CoreCount', 'ThreadCount', 'BaseClock', 'BoostClock', 'TDP', 'Socket']].copy()
    
    #print(tabulate(df, headers='keys', tablefmt='fancy_outline'))
    #print(tabulate(components_df, headers='keys', tablefmt='fancy_outline'))
    #print(tabulate(cpus_df, headers='keys', tablefmt='fancy_outline'))
    
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
            cpu_data = cpus_df.loc[_]
            cursor.execute(
                "INSERT INTO cpus (componentid, corecount, threadcount, baseclock, boostclock, tdp, socket) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (component_id, cpu_data['CoreCount'], cpu_data['ThreadCount'], cpu_data['BaseClock'], cpu_data['BoostClock'], cpu_data['TDP'], cpu_data['Socket'])
            )
        connection.commit()
    except Exception as e:
        print(f"DB 관련 에러: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()
            print("DB연결종료")
