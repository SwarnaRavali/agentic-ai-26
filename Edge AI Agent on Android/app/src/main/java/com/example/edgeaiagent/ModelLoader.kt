package com.example.edgeaiagent

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import java.io.File

const val FORCE_CPU = false

const val MODEL_FILE_NAME = "gemma-4-E2B-it.litertlm"

// FILE INFO: Loads the model. loadEngine finds the model file in the app's data folder
// and calls createEngine to build the engine that runs it.
// It tries the GPU first and falls back to the CPU (that is the "GPU"/"CPU" in the header)
fun loadEngine(context: Context): Pair<Engine, String> {
    val modelFile = File(context.getExternalFilesDir(null), MODEL_FILE_NAME)
    if (!modelFile.exists()) {
        Log.w(TAG, "Model file missing: $modelFile")
        throw ModelMissingException(
            "adb push $MODEL_FILE_NAME /sdcard/Android/data/${context.packageName}/files/"
        )
    }

    if (!FORCE_CPU) {
        try {
            return createEngine(context, modelFile, Backend.GPU(), "GPU") to "GPU"
        } catch (e: Exception) {
            Log.w(TAG, "GPU init failed, falling back to CPU", e)
        }
    }
    return createEngine(context, modelFile, Backend.CPU(), "CPU") to "CPU"
}

private fun createEngine(context: Context, modelFile: File, backend: Backend, label: String): Engine {
    Log.i(TAG, "init start ($label)")
    val t0 = SystemClock.elapsedRealtime()
    val eng = Engine(
        EngineConfig(
            modelPath = modelFile.path,
            backend = backend,
            cacheDir = context.cacheDir.path,
        )
    )
    try {
        eng.initialize()
    } catch (e: Exception) {
        eng.close()
        Log.e(TAG, "init failed ($label) after ${SystemClock.elapsedRealtime() - t0} ms")
        throw e
    }
    Log.i(TAG, "init end ($label) in ${SystemClock.elapsedRealtime() - t0} ms")
    return eng
}
