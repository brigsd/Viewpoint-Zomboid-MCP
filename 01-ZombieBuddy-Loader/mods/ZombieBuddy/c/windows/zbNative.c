#define WIN32_LEAN_AND_MEAN
#include <windows.h>

HMODULE hOrig = NULL;

#define ZB_JAR "ZombieBuddy.jar"
#define AGENT_OPTIONS_MAX 2048

// Minimal DllMain to prevent CRT initialization
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    return TRUE;
}

int  (*pAgent_OnAttach)(void*, char*, void*) = NULL;
int  (*pAgent_OnLoad)(void*, char*, void*)   = NULL;
void (*pAgent_OnUnload)(void*)               = NULL;

void write_msg(const char* msg) {
    WriteConsoleA(GetStdHandle(STD_OUTPUT_HANDLE), msg, lstrlenA(msg), NULL, NULL);
}

void init_instrument_dll() {
    if (hOrig) return; // already loaded

    SetDllDirectoryA(".\\jre64\\bin");
    hOrig = LoadLibraryA("instrument.dll");
    SetDllDirectoryA(NULL);

    if (!hOrig) {
        write_msg("[zbNative] Failed to load instrument.dll\n");
        return;
    }

    *(void**)&pAgent_OnAttach = GetProcAddress(hOrig, "Agent_OnAttach");
    *(void**)&pAgent_OnLoad   = GetProcAddress(hOrig, "Agent_OnLoad");
    *(void**)&pAgent_OnUnload = GetProcAddress(hOrig, "Agent_OnUnload");
}

void check_and_apply_update(const char* jarPath) {
    char newJarPath[1024];
    wsprintf(newJarPath, "%s.new", jarPath);

    // Check if .new file exists
    DWORD attrs = GetFileAttributesA(newJarPath);
    if (attrs == INVALID_FILE_ATTRIBUTES || (attrs & FILE_ATTRIBUTE_DIRECTORY)) {
        return; // No update pending
    }

    // Update is pending - apply it
    write_msg("[zbNative] Pending update detected, applying...\n");

    // Rename .new file to JAR file, replacing existing file if it exists
    if (MoveFileExA(newJarPath, jarPath, MOVEFILE_REPLACE_EXISTING)) {
        write_msg("[zbNative] Successfully applied update\n");
    } else {
        write_msg("[zbNative] Error: Failed to apply update\n");
    }
}

int build_agent_options(const char* tail, char* out, int outSize) {
    int jarLen = lstrlenA(ZB_JAR);
    int tailLen = tail == NULL ? 0 : lstrlenA(tail);
    int needsArgs = tailLen > 0;
    int totalLen = jarLen + (needsArgs ? 1 + tailLen : 0);

    if (totalLen + 1 > outSize) {
        write_msg("[zbNative] Error: agent options are too long\n");
        return 0;
    }

    lstrcpyA(out, ZB_JAR);
    if (needsArgs) {
        out[jarLen] = '=';
        lstrcpyA(out + jarLen + 1, tail);
    }
    return 1;
}

__declspec(dllexport) int Agent_OnLoad(void* jvm, char* tail, void* reserved) {
    if (hOrig == NULL) {
        init_instrument_dll();
    }
    if (!pAgent_OnLoad) {
        return -1;
    }

    // Check for pending update before loading the agent
    check_and_apply_update(ZB_JAR);

    char agentOptions[AGENT_OPTIONS_MAX];
    if (!build_agent_options(tail, agentOptions, sizeof(agentOptions))) {
        return -1;
    }

    return pAgent_OnLoad(jvm, agentOptions, reserved);
}

__declspec(dllexport) int Agent_OnAttach(void* jvm, char* args, void* reserved) {
    if (hOrig == NULL) {
        init_instrument_dll();
    }
    if (!pAgent_OnAttach) {
        return -1;
    }

    char agentOptions[AGENT_OPTIONS_MAX];
    if (!build_agent_options(args, agentOptions, sizeof(agentOptions))) {
        return -1;
    }

    return pAgent_OnAttach(jvm, agentOptions, reserved);
}

__declspec(dllexport) void Agent_OnUnload(void* jvm) {
    if (hOrig == NULL) {
        return;
    }
    if (pAgent_OnUnload) {
        pAgent_OnUnload(jvm);
    }

    FreeLibrary(hOrig);
    hOrig = NULL;
}

