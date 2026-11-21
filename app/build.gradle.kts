plugins {
    id("com.android.application")
}

android {
    namespace = "com.vitalens.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.vitalens.app"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }
}

dependencies {
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("androidx.health.connect:connect-client:1.1.0")
}