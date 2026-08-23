// Kotlin DSL, not the Groovy `settings.gradle` the M0 scaffold used.
//
// Flutter 3.47 generates `.gradle.kts` and its Gradle plugin no longer resolves correctly
// against the legacy Groovy files — the symptom was an unrelated-looking tool crash
// ("Could not determine run package name", flutter#169475) rather than a build error
// naming the DSL. A pristine `flutter create` project built fine with identical Kotlin and
// manifest sources, which is how the DSL was identified as the difference.
//
// Plugin versions are the ones `flutter create` emits for this Flutter version; they are
// mutually compatible with the Gradle in gradle-wrapper.properties and should be changed
// as a set, not individually.
pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            file("local.properties").inputStream().use { properties.load(it) }
            val flutterSdkPath = properties.getProperty("flutter.sdk")
            require(flutterSdkPath != null) { "flutter.sdk not set in local.properties" }
            flutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "9.1.0" apply false
    id("org.jetbrains.kotlin.android") version "2.4.0" apply false
}

include(":app")
