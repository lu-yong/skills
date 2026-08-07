---
name: adb
description: Android Debug Bridge workflows for device inspection, AOSP/vendor bring-up, HAL and service debugging, log collection, file transfer, property checks, shell commands, port forwarding, app/package operations, and safe multi-device adb command execution. Use when an agent needs to run or explain adb commands, diagnose Android devices, collect logs, inspect services, test native/vendor components, or interact with connected Android hardware/emulators.
---

# ADB

## Core Workflow

1. Confirm the adb target before running device-affecting commands.
   - Use `adb devices -l` first when device state is unknown.
   - Use `adb -s <serial> ...` whenever more than one device or emulator is connected.
   - Prefer read-only inspection commands before mutating device state.

2. Match commands to the device state.
   - If the device is `unauthorized`, tell the user to accept the RSA prompt on the device.
   - If the device is `offline`, restart adb with `adb kill-server` then `adb start-server`, reconnect USB, or retry the emulator.
   - If `adb root` is needed, run it only on debug/userdebug/eng builds where it is expected to work.

3. Collect evidence in layers.
   - Start with `getprop`, `dumpsys`, `service list`, `lshal` or `cmd` depending on the subsystem.
   - Use `logcat`, `dmesg`, and tombstones for failures.
   - For SELinux issues, check `getenforce`, `dmesg`, and audit denials.

4. Preserve user/device safety.
   - Do not run destructive commands such as wipe, uninstall, remount, setprop changes, reboot, or writes under `/data`, `/vendor`, `/system`, or `/dev` unless the user asked for that action or the command is clearly required.
   - Avoid exposing secrets from logs, properties, accounts, tokens, or private app data in final answers.
   - Explain commands that change device state before running them.

## Command Reference

For concrete command patterns, load [references/adb-command-patterns.md](references/adb-command-patterns.md). Use it for:

- device selection and connection issues
- logs, bugreports, tombstones, and kernel messages
- AOSP/vendor/HAL service inspection
- file transfer and shell workflows
- package/app operations
- port forwarding and networking
- SELinux and `/dev` node diagnostics

## Output Style

When reporting results, include:

- the target serial if a command used `-s`
- the exact command when it matters for reproducibility
- the key observed lines or a concise summary of long output
- any command that could not be run and why
