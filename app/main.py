from app.core.config import settings

def run():
    print(f"Invyntra environment: {settings.ENV}")
    print(f"App Name: {settings.APP_NAME}")
    print(f"Debug: {settings.DEBUG}")

if __name__ == "__main__":
    run()
