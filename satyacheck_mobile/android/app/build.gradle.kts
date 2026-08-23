plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.satyacheck"

    // `flutter.compileSdkVersion` / `flutter.ndkVersion` rather than literals: Flutter
    // picks values it has actually validated against this SDK install. Pinning literals is
    // how the earlier build ended up demanding `platforms;android-34` and
    // `ndk;27.0.12077973`, neither of which Google's repository still publishes.
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.satyacheck"

        // minSdk comes from Flutter (currently 24). The app cannot work below 23 in any
        // case: RECORD_AUDIO and READ_PHONE_STATE are runtime permissions from 23, and the
        // request flow in MainActivity has no pre-23 path.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: a real signing config before any release build ships.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    sourceSets {
        // Unit tests live beside the Kotlin sources rather than under java/.
        getByName("test").java.srcDirs("src/test/kotlin")
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // ContextCompat.startForegroundService and the permission checks in MainActivity.
    implementation("androidx.core:core-ktx:1.13.1")

    // RingBufferTest runs on the JVM, no device required:
    //   ./gradlew :app:testDebugUnitTest
    testImplementation("junit:junit:4.13.2")
}
