#!/bin/sh
# Build the example APK without Gradle: aapt2 (manifest only) + javac + d8 + apksigner (debug key).
set -e
cd "$(dirname "$0")"
SDK=${ANDROID_HOME:-$HOME/Library/Android/sdk}; BT=$SDK/build-tools/37.0.0; JAR=$SDK/platforms/android-34/android.jar
OUT=${1:-build}; rm -rf "$OUT"; mkdir -p "$OUT/classes" "$OUT/dex"
"$BT/aapt2" link -o "$OUT/unsigned.apk" --manifest AndroidManifest.xml -I "$JAR"
javac --release 11 -cp "$JAR" -d "$OUT/classes" $(find src -name '*.java') 2>/dev/null || \
  javac -source 11 -target 11 -cp "$JAR" -d "$OUT/classes" $(find src -name '*.java')
"$BT/d8" --lib "$JAR" --min-api 26 --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')
cp "$OUT/unsigned.apk" "$OUT/app.apk" && (cd "$OUT/dex" && zip -q -j ../app.apk classes.dex)
[ -f debug.keystore ] || keytool -genkeypair -keystore debug.keystore -storepass android -keypass android \
  -alias debug -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Teardown Example" >/dev/null 2>&1
"$BT/zipalign" -f 4 "$OUT/app.apk" "$OUT/aligned.apk"
"$BT/apksigner" sign --ks debug.keystore --ks-pass pass:android --out "$OUT/tipper-b.apk" "$OUT/aligned.apk"
echo "$OUT/tipper-b.apk"
