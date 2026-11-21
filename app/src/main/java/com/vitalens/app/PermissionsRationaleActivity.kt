package com.vitalens.app

import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity

class PermissionsRationaleActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 80, 48, 48)
        }

        val title = TextView(this).apply {
            text = "Vitalens Health Data"
            textSize = 28f
        }

        val message = TextView(this).apply {
            text = """
                Vitalens reads health and fitness data from Health Connect to provide a unified view of your wearable data.

                Vitalens currently requests access to your step count.

                Your health data is used only to provide the features of Vitalens.
            """.trimIndent()

            textSize = 18f
        }

        layout.addView(title)
        layout.addView(message)

        setContentView(layout)
    }
}