plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.wxauto.reply"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.wxauto.reply"
        minSdk = 26          // RemoteInput 直接回复在 API 24+ 可用，26 起行为才稳定
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")

    // 引擎单测（纯 JVM，不需要设备）
    testImplementation("junit:junit:4.13.2")
    // Android 平台自带 org.json；JVM 单测没有可执行实现，导入画像的严格解析需用它验证。
    testImplementation("org.json:json:20240303")
}
