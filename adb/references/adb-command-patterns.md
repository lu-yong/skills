# ADB Command Patterns

## Device Selection

```bash
adb devices -l
adb -s <serial> get-state
adb -s <serial> shell getprop ro.build.type
```

Use `-s <serial>` for every command when multiple devices are connected.

## Server And Connection Recovery

```bash
adb kill-server
adb start-server
adb reconnect
adb reconnect device
adb reconnect offline
adb tcpip 5555
adb connect <ip>:5555
adb disconnect <ip>:5555
```

Use TCP adb only when the user expects network debugging.

## Shell And Properties

```bash
adb -s <serial> shell
adb -s <serial> shell id
adb -s <serial> shell uname -a
adb -s <serial> shell getprop
adb -s <serial> shell getprop <property>
adb -s <serial> shell setprop <property> <value>
```

Treat `setprop` as state-changing.

## Root, Remount, And Reboot

```bash
adb -s <serial> root
adb -s <serial> unroot
adb -s <serial> remount
adb -s <serial> reboot
adb -s <serial> reboot bootloader
adb -s <serial> reboot recovery
```

Run these only when the user asked or the workflow clearly requires them.

## Logs And Crash Evidence

```bash
adb -s <serial> logcat -d
adb -s <serial> logcat -c
adb -s <serial> logcat -v threadtime
adb -s <serial> logcat -b all -d
adb -s <serial> bugreport bugreport.zip
adb -s <serial> shell dmesg
adb -s <serial> shell ls -l /data/tombstones
adb -s <serial> pull /data/tombstones ./tombstones
```

Prefer `logcat -d` for snapshots and live `logcat` only when actively watching reproduction.

## Files

```bash
adb -s <serial> push <local> <remote>
adb -s <serial> pull <remote> <local>
adb -s <serial> shell ls -l <path>
adb -s <serial> shell cat <path>
adb -s <serial> shell chmod <mode> <path>
adb -s <serial> shell chown <owner>:<group> <path>
```

Treat `chmod`, `chown`, and writes under system/vendor/data/dev paths as state-changing.

## Packages And Apps

```bash
adb -s <serial> install -r <apk>
adb -s <serial> uninstall <package>
adb -s <serial> shell pm list packages
adb -s <serial> shell pm path <package>
adb -s <serial> shell am start -n <package>/<activity>
adb -s <serial> shell am force-stop <package>
```

Avoid uninstalling or clearing user data unless requested.

## Services, Binder, And HALs

```bash
adb -s <serial> shell service list
adb -s <serial> shell dumpsys
adb -s <serial> shell dumpsys <service>
adb -s <serial> shell cmd -l
adb -s <serial> shell lshal
adb -s <serial> shell ps -A
adb -s <serial> shell ps -A -Z
```

For AIDL HALs on recent Android releases, check service manager visibility with `service list`, subsystem-specific `cmd` tools, process state with `ps -A -Z`, and VINTF/manifest artifacts from the build tree when available.

## SELinux And Device Nodes

```bash
adb -s <serial> shell getenforce
adb -s <serial> shell ls -lZ /dev/<node>
adb -s <serial> shell dmesg | grep -i avc
adb -s <serial> logcat -b all -d | grep -i avc
adb -s <serial> shell ps -A -Z | grep <service>
```

For `/dev/hello` style HAL debugging, inspect node ownership, SELinux label, service process domain, and AVC denials before changing policy.

## Networking And Port Forwarding

```bash
adb -s <serial> forward tcp:<host-port> tcp:<device-port>
adb -s <serial> forward --list
adb -s <serial> forward --remove tcp:<host-port>
adb -s <serial> reverse tcp:<device-port> tcp:<host-port>
adb -s <serial> reverse --list
adb -s <serial> shell ip addr
```

Remove forwards/reverses after temporary debugging when they are no longer needed.
