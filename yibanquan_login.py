from playwright.sync_api import sync_playwright
import ddddocr


def login(account, password):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto('https://rzagent.yibanquan.com.cn/system/index.do')

        page.fill('input[name="loginName"]', account)
        page.fill('input[name="loginPwd"]', password)

        # 获取验证码图片并 OCR 识别
        ocr = ddddocr.DdddOcr(show_ad=False)
        for _ in range(3):  # 最多重试3次
            captcha_bytes = page.locator('img#verifyCodeImg').screenshot()
            code = ocr.classification(captcha_bytes)
            page.fill('input[name="verifyCode"]', code)
            page.check('input[type="checkbox"]')  # 同意隐私政策
            page.click('button:has-text("登 录")')

            # 检查是否登录成功
            if 'index.do' not in page.url or page.locator('.error').count() == 0:
                break
            # 失败则换一张验证码重试
            page.click('text=看不清？换一张')

        return browser, page


if __name__ == '__main__':
    browser, page = login('your_account', 'your_password')
    input('Press Enter to exit...')
    browser.close()
