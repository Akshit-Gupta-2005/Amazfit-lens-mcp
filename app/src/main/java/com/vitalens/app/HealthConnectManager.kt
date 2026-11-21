package com.vitalens.app

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

data class HealthSummary(
    val steps: Long,
    val distanceMeters: Double?,
    val activeCalories: Double?,
    val averageHeartRate: Long?,
    val restingHeartRate: Long?,
    val averageHrv: Double?,
    val averageSpo2: Double?,
    val sleepSessions: List<SleepSummary>,
    val exerciseSessions: List<ExerciseSummary>
)

data class SleepSummary(
    val startTime: Instant,
    val endTime: Instant,
    val durationMinutes: Long
)

data class ExerciseSummary(
    val startTime: Instant,
    val endTime: Instant,
    val type: String,
    val durationMinutes: Long
)

class HealthConnectManager(context: Context) {

    private val client =
        HealthConnectClient.getOrCreate(context)

    val requiredPermissions = setOf(
        HealthPermission.getReadPermission(
            StepsRecord::class
        ),
        HealthPermission.getReadPermission(
            DistanceRecord::class
        ),
        HealthPermission.getReadPermission(
            ActiveCaloriesBurnedRecord::class
        ),
        HealthPermission.getReadPermission(
            HeartRateRecord::class
        ),
        HealthPermission.getReadPermission(
            RestingHeartRateRecord::class
        ),
        HealthPermission.getReadPermission(
            HeartRateVariabilityRmssdRecord::class
        ),
        HealthPermission.getReadPermission(
            OxygenSaturationRecord::class
        ),
        HealthPermission.getReadPermission(
            SleepSessionRecord::class
        ),
        HealthPermission.getReadPermission(
            ExerciseSessionRecord::class
        )
    )

    suspend fun getGrantedPermissions(): Set<String> {
        return client.permissionController
            .getGrantedPermissions()
    }

    suspend fun getRecentSummary(days: Long = 7): HealthSummary {

    val zone = ZoneId.systemDefault()

    val end = Instant.now()

    val start = LocalDate
        .now(zone)
        .minusDays(days - 1)
        .atStartOfDay(zone)
        .toInstant()

    val timeRange =
        TimeRangeFilter.between(start, end)

    val aggregateResult = client.aggregate(
        AggregateRequest(
            metrics = setOf(
                StepsRecord.COUNT_TOTAL,
                DistanceRecord.DISTANCE_TOTAL,
                ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL,
                HeartRateRecord.BPM_AVG,
                RestingHeartRateRecord.BPM_AVG
            ),
            timeRangeFilter = timeRange
        )
    )

    val steps =
        aggregateResult[
            StepsRecord.COUNT_TOTAL
        ] ?: 0L

    val distance =
        aggregateResult[
            DistanceRecord.DISTANCE_TOTAL
        ]?.inMeters?.toDouble()

    val activeCalories =
        aggregateResult[
            ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL
        ]?.inKilocalories?.toDouble()

    val averageHeartRate =
        aggregateResult[
            HeartRateRecord.BPM_AVG
        ]

    val restingHeartRate =
        aggregateResult[
            RestingHeartRateRecord.BPM_AVG
        ]

    val averageHrv =
        getAverageHrv(start, end)

    val averageSpo2 =
        getAverageSpo2(start, end)

    val sleepSessions =
        getSleepSessions(start, end)

    val exerciseSessions =
        getExerciseSessions(start, end)

    return HealthSummary(
        steps = steps,
        distanceMeters = distance,
        activeCalories = activeCalories,
        averageHeartRate = averageHeartRate,
        restingHeartRate = restingHeartRate,
        averageHrv = averageHrv,
        averageSpo2 = averageSpo2,
        sleepSessions = sleepSessions,
        exerciseSessions = exerciseSessions
    )
}

    private suspend fun getAverageHrv(
        start: Instant,
        end: Instant
    ): Double? {

        val response = client.readRecords(
            ReadRecordsRequest(
                recordType =
                    HeartRateVariabilityRmssdRecord::class,
                timeRangeFilter =
                    TimeRangeFilter.between(start, end)
            )
        )

        if (response.records.isEmpty()) {
            return null
        }

        return response.records
            .map {
                it.heartRateVariabilityMillis
                    .toDouble()
            }
            .average()
    }

    private suspend fun getAverageSpo2(
        start: Instant,
        end: Instant
    ): Double? {

        val response = client.readRecords(
            ReadRecordsRequest(
                recordType =
                    OxygenSaturationRecord::class,
                timeRangeFilter =
                    TimeRangeFilter.between(start, end)
            )
        )

        if (response.records.isEmpty()) {
            return null
        }

        return response.records
            .map {
                it.percentage.value
            }
            .average()
    }

    private suspend fun getSleepSessions(
        start: Instant,
        end: Instant
    ): List<SleepSummary> {

        val response = client.readRecords(
            ReadRecordsRequest(
                recordType =
                    SleepSessionRecord::class,
                timeRangeFilter =
                    TimeRangeFilter.between(start, end)
            )
        )

        return response.records.map {
            SleepSummary(
                startTime = it.startTime,
                endTime = it.endTime,
                durationMinutes =
                    Duration.between(
                        it.startTime,
                        it.endTime
                    ).toMinutes()
            )
        }
    }

    private suspend fun getExerciseSessions(
        start: Instant,
        end: Instant
    ): List<ExerciseSummary> {

        val response = client.readRecords(
            ReadRecordsRequest(
                recordType =
                    ExerciseSessionRecord::class,
                timeRangeFilter =
                    TimeRangeFilter.between(start, end)
            )
        )

        return response.records.map {
            ExerciseSummary(
                startTime = it.startTime,
                endTime = it.endTime,
                type = it.exerciseType.toString(),
                durationMinutes =
                    Duration.between(
                        it.startTime,
                        it.endTime
                    ).toMinutes()
            )
        }
    }
}