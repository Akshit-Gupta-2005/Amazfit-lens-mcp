package com.vitalens.app

import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.contracts.HealthPermissionsRequestContract
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var healthConnectManager: HealthConnectManager

    private lateinit var statusText: TextView
    private lateinit var dataText: TextView

    private val permissionLauncher =
        registerForActivityResult(
            HealthPermissionsRequestContract()
        ) { grantedPermissions ->

            if (
                grantedPermissions.containsAll(
                    healthConnectManager.requiredPermissions
                )
            ) {
                statusText.text = "Health Connect connected."
                readHealthData()
            } else {
                statusText.text = "Some permissions were not granted."
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        healthConnectManager = HealthConnectManager(this)

        createUi()
        checkPermissions()
    }

    private fun createUi() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 80, 48, 48)
        }

        val title = TextView(this).apply {
            text = "Vitalens"
            textSize = 32f
        }

        statusText = TextView(this).apply {
            text = "Checking Health Connect..."
            textSize = 18f
        }

        dataText = TextView(this).apply {
            text = "No data loaded."
            textSize = 18f
        }

        val connectButton = Button(this).apply {
            text = "Connect Health Connect"
            setOnClickListener {
                requestPermissions()
            }
        }

        val refreshButton = Button(this).apply {
            text = "Refresh Data"
            setOnClickListener {
                readHealthData()
            }
        }

        layout.addView(title)
        layout.addView(statusText)
        layout.addView(dataText)
        layout.addView(connectButton)
        layout.addView(refreshButton)

        setContentView(layout)
    }

    private fun checkPermissions() {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val granted =
                    healthConnectManager.getGrantedPermissions()

                if (
                    granted.containsAll(
                        healthConnectManager.requiredPermissions
                    )
                ) {
                    statusText.text =
                        "Health Connect connected."

                    readHealthData()
                } else {
                    statusText.text =
                        "Additional permissions required."
                }
            } catch (e: Exception) {
                statusText.text =
                    "Permission check failed: ${e.message}"
            }
        }
    }

    private fun requestPermissions() {
        permissionLauncher.launch(
            healthConnectManager.requiredPermissions
        )
    }

    private fun readHealthData() {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                statusText.text =
                    "Reading Health Connect..."

                val data =
                    healthConnectManager.getRecentSummary(7)

                val text = buildString {
                    appendLine("Last 7 days health")
                    appendLine()

                    appendLine(
                        "Steps: ${data.steps}"
                    )

                    data.distanceMeters?.let {
                        appendLine(
                            "Distance: " +
                                "%.2f".format(it / 1000.0) +
                                " km"
                        )
                    }

                    data.activeCalories?.let {
                        appendLine(
                            "Active calories: " +
                                "%.0f".format(it) +
                                " kcal"
                        )
                    }

                    data.averageHeartRate?.let {
                        appendLine(
                            "Average heart rate: " +
                                "$it bpm"
                        )
                    }

                    data.restingHeartRate?.let {
                        appendLine(
                            "Resting heart rate: " +
                                "$it bpm"
                        )
                    }

                    data.averageHrv?.let {
                        appendLine(
                            "Average HRV: " +
                                "%.1f".format(it) +
                                " ms"
                        )
                    }

                    data.averageSpo2?.let {
                        appendLine(
                            "Average SpO2: " +
                                "%.1f".format(it) +
                                "%"
                        )
                    }

                    appendLine()

                    appendLine(
                        "Sleep sessions: " +
                            data.sleepSessions.size
                    )

                    data.sleepSessions.forEach {
                        appendLine(
                            "  ${it.durationMinutes} min"
                        )
                    }

                    appendLine()

                    appendLine(
                        "Exercise sessions: " +
                            data.exerciseSessions.size
                    )

                    data.exerciseSessions.forEach {
                        appendLine(
                            "  ${it.type}: " +
                                "${it.durationMinutes} min"
                        )
                    }
                }

                dataText.text = text

                statusText.text =
                    "Data read successfully."

            } catch (e: Exception) {

                e.printStackTrace()

                statusText.text =
                    "Failed: ${e::class.java.name}"

                dataText.text =
                    e.stackTraceToString()
            }
        }
    }
}