import time
import csv
from datetime import datetime
import pytz
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup as bs
import os
import re
import sys

# ตั้งค่าการบันทึก log
log_filename = 'app.log'
logging.basicConfig(level=logging.INFO, filename=log_filename, filemode='w', format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8-sig')

# ตั้งค่า timezone เป็น Asia/Bangkok
def current_time():
    bangkok_tz = pytz.timezone('Asia/Bangkok')
    return datetime.now(bangkok_tz)

# Read credentials from file
def read_credentials():
    credentials = {}
    with open('credential.txt', 'r') as f:
        lines = f.readlines()
    for line in lines:
        if '=' in line:
            key, value = line.strip().split(' = ', 1)
            credentials[key] = value
    return credentials

# ตั้งค่า Chrome options
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--remote-debugging-port=9222')
chrome_options.add_argument('--window-size=1920x1080')
chrome_options.add_argument('--disable-software-rasterizer')
chrome_options.add_argument('--lang=th')

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def login(email, password):
    logging.info("Attempting to log in...")
    driver.get('https://www.facebook.com/login/')
    try:
        email_input = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.NAME, 'email')))
        logging.info("Email input found")
        password_input = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.NAME, 'pass')))
        logging.info("Password input found")
        login_button = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.NAME, 'login')))
        logging.info("Login button found")
        
        email_input.send_keys(email)
        password_input.send_keys(password)
        logging.info(f"Email: {email}")
        logging.info(f"Password: {password}")
        login_button.click()
        
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[aria-label="Facebook"]')))
        logging.info("Logged in successfully.")
    except TimeoutException:
        logging.error("Login failed due to timeout.")
        driver.save_screenshot('login_timeout.png')
        driver.quit()
        sys.exit()
    except Exception as e:
        logging.error(f"Login failed: {str(e)}")
        driver.save_screenshot('login_error.png')
        driver.quit()
        sys.exit()

def load_existing_posts(output_file):
    posts = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    post_key = row['Post']
                    posts[post_key] = row
        except FileNotFoundError:
            pass
    return posts

def convert_numbers(text):
    try:
        number = re.findall(r'\d+\.?\d*', text)[0]  # หาค่าตัวเลขที่เป็นทศนิยมหรือจำนวนเต็ม
        number = float(number)
        if 'พัน' in text or 'K' in text:
            return number * 1000
        elif 'หมื่น' in text:
            return number * 10000
        elif 'แสน' in text:
            return number * 100000
        elif 'ล้าน' in text or 'M' in text:
            return number * 1000000
        return number
    except IndexError:
        logging.error(f"Error converting number: {text}")
        return 0

def extract_number(text):
    thai_numerals = ['พัน', 'หมื่น', 'แสน', 'ล้าน', 'K', 'M']
    for numeral in thai_numerals:
        if numeral in text:
            return str(convert_numbers(text))
    try:
        return str(float(re.findall(r'\d+\.?\d*', text)[0]))
    except IndexError:
        return '0'

def save_to_csv(post_html, existing_posts, output_file):
    try:
        post_text_div = post_html.find('div', {'data-ad-preview': 'message'})
        post_text = post_text_div.get_text(strip=True).replace('\n', ' ').replace('\r', ' ') if post_text_div else ""

        image_post_div = post_html.find('div', {'class': 'x6s0dn4 x78zum5 xdt5ytf x5yr21d xl56j7k x10l6tqk x17qophe x13vifvy xh8yej3'})
        image_post_text = image_post_div.get_text(strip=True).replace('\n', ' ').replace('\r', ' ') if image_post_div else ""

        if not post_text and image_post_text:
            post_text = image_post_text
        elif not post_text:
            post_text = " "

        reaction_span = post_html.find_all('span', {'class': 'xrbpyxo x6ikm8r x10wlt62 xlyipyv x1exxlbk'})
        reactions = int(float(extract_number(reaction_span[0].get_text(strip=True)))) if reaction_span else 0

        comment_div = post_html.find_all('div', {'class': 'x9f619 x1n2onr6 x1ja2u2z x78zum5 x2lah0s x1qughib x1qjc9v5 xozqiw3 x1q0g3np xykv574 xbmpl8g x4cne27 xifccgj'})
        if comment_div:
            logging.info(f"Comment div found for post: {post_text[:30]}")
            comment_spans = comment_div[0].find_all('span')
            comments_count = '0'
            for span in comment_spans:
                if 'ความคิดเห็น' in span.get_text(strip=True) or 'comments' in span.get_text(strip=True):
                    logging.info(f"Comment span found for post: {post_text[:30]}")
                    comments_count = int(float(extract_number(span.get_text(strip=True))))
                    break
            else:
                logging.info(f"No relevant comment span found for post: {post_text[:30]}")
        else:
            logging.info(f"No comment div found for post: {post_text[:30]}")
            comments_count = 0

        shares_div = post_html.find_all('div', {'class': 'x1i10hfl x1qjc9v5 xjqpnuy xa49m3k xqeqjp1 x2hbi6w x1ypdohk xdl72j9 x2lah0s xe8uvvx x2lwn1j xeuugli xggy1nq x1t137rt x1o1ewxj x3x9cwd x1e5q0jg x13rtm0m x3nfvp2 x1q0g3np x87ps6o x1lku1pv x1a2a7pz xjyslct xjbqb8w x13fuv20 xu3j5b3 x1q0q8m5 x26u7qi x972fbf xcfux6l x1qhh985 xm0m39n x9f619 x1heor9g xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1n2onr6 x16tdsg8 xt0b8zv x1hl2dhg x1ja2u2z'})
        shares = int(float(extract_number(shares_div[0].get_text(strip=True)))) if shares_div else 0

        new_data = {
            'Date': current_time().strftime('%Y-%m-%d %H:%M:%S'),
            'Post': post_text,
            'Reactions': reactions,
            'Comments': comments_count,
            'Shares': shares
        }
        existing_posts[post_text] = new_data

        with open(output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['Date', 'Post', 'Reactions', 'Comments', 'Shares']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for post in existing_posts.values():
                writer.writerow(post)
    except Exception as e:
        logging.error(f"Failed to save post to CSV: {e}")

def extract_data(driver, existing_posts, output_file):
    try:
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, "//div[@role='article']")))
        
        see_more_list = driver.find_elements(By.XPATH, "//*[contains(text(), 'See more') or contains(text(), 'ดูเพิ่มเติม')]")
        for s in see_more_list:
            driver.execute_script("arguments[0].click();", s)
            time.sleep(2)

        article_list = driver.find_elements(By.XPATH, "//div[@role='article']")
        for a in article_list:
            post_html = bs(a.get_attribute('outerHTML'), 'html.parser')
            save_to_csv(post_html, existing_posts, output_file)

        new_height = driver.execute_script("return document.body.scrollHeight")
        return new_height
    except Exception as e:
        logging.error(f"Error in extract_data: {str(e)}")
        return 'err'

def scroll(existing_posts, output_file, PAUSE_TIME):
    new_height = extract_data(driver, existing_posts, output_file)
    driver.execute_script("window.scrollTo({ left: 0, top: document.body.clientHeight, behavior: 'smooth' })")
    new_height = driver.execute_script("return document.body.scrollHeight")
    time.sleep(PAUSE_TIME)
    return new_height

def get_data(email, password, group_url, output_file, PAUSE_TIME, MINUTES):
    logging.info("Navigating to the group URL...")
    driver.get(group_url)
    time.sleep(15)

    last_height = 1
    existing_posts = load_existing_posts(output_file)
    start_time = time.time()

    while True:
        new_height = scroll(existing_posts, output_file, PAUSE_TIME)
        if new_height == last_height or new_height == 'err' or (time.time() - start_time) > (MINUTES * 60):
            break
        last_height = new_height
        time.sleep(2)

    logging.info("Data extraction complete.")
    driver.quit()
    sys.exit()
    
def main():
    credentials = read_credentials()
    email = credentials['email']
    password = credentials['password']
    group_url = credentials['group_url']
    output_file = credentials['output_file']

    PAUSE_TIME = 10  # Time to pause between scrolls
    MINUTES = 2  # Total time to run the extraction in minutes
    
    login(email, password)
    get_data(email, password, group_url, output_file, PAUSE_TIME, MINUTES)

