@echo off
rem Network probe sample -- drives the T0/T1/T2 network-policy tests.
rem
rem Exercises three egress paths, each with a BOUNDED timeout so a fully
rem isolated guest does not stall the collection cycle:
rem   [1] ICMP  -> 8.8.8.8
rem   [2] DNS   -> www.example.com (via whatever resolver the guest has)
rem   [3] TCP   -> 1.1.1.1:80
rem
rem The point is NOT to succeed. The point is to make the guest *try*, so the
rem host-side sniffer has something to see (or provably not see).
setlocal
echo NET-PROBE-START

echo [1] ICMP 8.8.8.8
ping -n 1 -w 1500 8.8.8.8

echo [2] DNS www.example.com
nslookup -timeout=2 -retry=1 www.example.com

echo [3] TCP 1.1.1.1:80
powershell -NoProfile -NonInteractive -Command "try{$c=New-Object Net.Sockets.TcpClient;$t=$c.ConnectAsync('1.1.1.1',80);if($t.Wait(3000)){'tcp=connected'}else{'tcp=timeout'};$c.Close()}catch{'tcp=error: '+$_.Exception.InnerException.Message}"

echo NET-PROBE-END
endlocal
exit /b 0
