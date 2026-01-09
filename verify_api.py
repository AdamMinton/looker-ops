import looker_sdk
import sys
import os
import configparser

def verify_access():
    print("Inspecting looker.ini sections...")
    config = configparser.ConfigParser()
    try:
        config.read("looker.ini")
        print(f"Found sections: {config.sections()}")
    except Exception as e:
        print(f"Error reading looker.ini: {e}")

    print("\nVerifying Looker API access...")
    try:
        # Try to guess the section if 'Test' isn't explicitly there but something obvious is
        section = "Test"
        if "Test" not in config.sections():
            # If there's only one section, maybe use that?
            # Or if there is a 'Looker' section.
            if "Looker" in config.sections():
                section = "Looker"
            elif len(config.sections()) > 0:
                 section = config.sections()[0]
                 print(f"Defaulting to first found section: {section}")
        
        print(f"Using section: {section}")
        sdk = looker_sdk.init40("looker.ini", section=section)
        me = sdk.me()
        print(f"Successfully connected as {me.display_name} (ID: {me.id})")
        print(f"Base URL: {sdk.auth.settings.base_url}")
    except Exception as e:
        print(f"Failed to connect to Looker API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_access()
