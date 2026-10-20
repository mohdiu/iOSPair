import sys

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # Used by CI to check the frozen build imports and can reach usbmux code.
        import asyncio

        from iospair import core

        try:
            print(asyncio.run(core.list_devices()))
        except core.AppleServiceMissing:
            print("selftest ok (Apple Mobile Device Service not running)")
        sys.exit(0)

    from iospair.app import main

    main()
