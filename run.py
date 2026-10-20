import sys

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # CI check of the frozen build: `--selftest [OUT_DIR]` pairs with the first device into OUT_DIR.
        import asyncio
        from pathlib import Path

        from iospair import core

        async def selftest():
            try:
                devices = await core.list_devices()
            except core.AppleServiceMissing:
                return 0
            if len(sys.argv) <= sys.argv.index("--selftest") + 1:
                return 0
            out = Path(sys.argv[sys.argv.index("--selftest") + 1])
            result = await core.generate(devices[0].udid, out, lambda _key: None)
            return 0 if len(result.files) == len(core.OUTPUT_NAMES) and result.wifi_enabled else 1

        sys.exit(asyncio.run(selftest()))

    from iospair.app import main

    main()
