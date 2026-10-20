# iOSPair

برنامج ويندوز بسيط يطلّع **ملف الاقتران (Pairing File)** للآيفون والآيباد بضغطة زر واحدة.

## التحميل
من صفحة **Releases** أو من **Actions → آخر بناء → Artifacts**:
- `iOSPair-Setup.exe` — مثبّت (بدون صلاحيات مدير)
- `iOSPair-Portable.exe` — نسخة تشتغل بدون تثبيت

## الاستخدام
1. ثبّت **iTunes** مرة وحدة بس (عشان ويندوز يتعرف على الجوال) — البرنامج يعطيك الرابط إذا ما كان مثبت.
2. وصّل الجوال بكيبل USB وافتح البرنامج.
3. يبدأ تلقائيًا أول ما يتعرف على الجوال ← افتح قفل الجوال ← اضغط **وثوق (Trust)** واكتب الرمز.
   (زر **طلّع ملف الاقتران** موجود لو تبي ملف جديد ثاني.)
4. يفتح لك المجلد تلقائيًا (على سطح المكتب: `iOSPair`).

## الملفات اللي تطلع
نفس الاقتران بأكثر من اسم، كل تطبيق ياخذ اللي يناسبه:

| الملف | التطبيق |
|---|---|
| `<UDID>.mobiledevicepairing` | SideStore / AltStore |
| `ALTPairingFile.mobiledevicepairing` | SideStore / AltStore |
| `<UDID>.plist` | StikDebug / Jitterbug / LiveContainer |
| `pairingFile.plist` | Feather / StikDebug |

**بدون تعارض:** كل ضغطة تسوي اقتران جديد بقيم مختلفة (HostID و SystemBUID عشوائية)، وما يلمس اقتران iTunes
ولا الملفات اللي طلّعتها قبل. كل مرة تنحفظ في مجلد جديد باسم الجوال والتاريخ.

ويفعّل تلقائيًا الاتصال عبر الواي فاي (EnableWifiConnections) اللي يحتاجه SideStore.

## الأنظمة المدعومة
- **الكمبيوتر:** Windows 10 و 11 (64-bit).
- **الجوال:** iOS 16 فما فوق (بما فيها 17 و 18 و 26)، وكذلك الأنظمة الأقدم من iOS 7 إلى iOS 15 —
  الاقتران نفسه يشتغل عليها. تأكد بس إن التطبيق اللي بتستخدم معه الملف يدعم إصدار جوالك.

## البناء من الكود
```bat
build.bat
```
أو تلقائيًا عبر GitHub Actions عند كل push، ويطلع Release عند أي tag يبدأ بـ `v`.

مبني على [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)، والفكرة من
[idevice_pair](https://github.com/jkcoxson/idevice_pair) و jitterbugpair.
