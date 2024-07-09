using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.NetworkInformation;
using System.Net;
using System.Threading.Tasks;
using System.Net.Sockets;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
namespace NetworkMonitor.Processor.Services;

public class NetworkUtils
{
    public static (string, string) GetLocalIPAddressAndSubnetMask(ILogger logger, LocalScanProcessorStates scanProcessorStates)
    {
        var message = "Searching for appropriate network interface...\n";
        logger.LogInformation(message);
        scanProcessorStates.RunningMessage += message;

        foreach (NetworkInterface ni in NetworkInterface.GetAllNetworkInterfaces())
        {
            message = $"Checking interface: {ni.Name}, Type: {ni.NetworkInterfaceType}, OperationalStatus: {ni.OperationalStatus}\n";
            logger.LogInformation(message);
            scanProcessorStates.RunningMessage += message;
            if (ni.OperationalStatus != OperationalStatus.Up ||
                ni.NetworkInterfaceType == NetworkInterfaceType.Loopback ||
                ni.Description.IndexOf("virtual", StringComparison.OrdinalIgnoreCase) >= 0 ||
                ni.NetworkInterfaceType == NetworkInterfaceType.Tunnel)
            {
                message = "Skipping this interface.\n";
                logger.LogInformation(message);
                scanProcessorStates.RunningMessage += message;
                continue;
            }

            // Prioritize Ethernet and Wireless interfaces
            if (ni.NetworkInterfaceType != NetworkInterfaceType.Ethernet &&
                ni.NetworkInterfaceType != NetworkInterfaceType.Wireless80211)
            {
                message = "Not an Ethernet or Wi-Fi interface, will use only if no better option found.\n";
                logger.LogInformation(message);
                scanProcessorStates.RunningMessage += message;
                continue;
            }

            var ipProperties = ni.GetIPProperties();
#if WINDOWS
            // Check for default gateway
            if (!ipProperties.GatewayAddresses.Any())
            {
                message= "No default gateway found, skipping.\n";
                 _logger.LogInformation(message);
        _scanProcessorStates.RunningMessage += message;
                continue;
            }
#endif

            foreach (UnicastIPAddressInformation ip in ipProperties.UnicastAddresses)
            {
                if (ip.Address.AddressFamily == AddressFamily.InterNetwork &&
                    !IPAddress.IsLoopback(ip.Address))
                {
                    message = $"Selected IP: {ip.Address}, Subnet Mask: {ip.IPv4Mask}\n";
                    logger.LogInformation(message);
                    scanProcessorStates.RunningMessage += message;
                    return (ip.Address.ToString(), ip.IPv4Mask.ToString());
                }
            }
        }

        throw new Exception("No suitable local IP Address and Subnet Mask found!\n");

    }
    public static (int networkAddress, int startIP, int endIP) GetNetworkRange(string ipAddress, string subnetMask)
    {
        int ipInt = IpToInt(ipAddress);
        int maskInt = IpToInt(subnetMask);

        int networkAddress = ipInt & maskInt;
        int broadcastAddress = networkAddress | ~maskInt;

        int startIP = 1; // Network address + 1
        int endIP = broadcastAddress - networkAddress - 1; // Broadcast address - network address - 1

        return (networkAddress, startIP, endIP);
    }

    public static int IpToInt(string ipAddress)
    {
        return BitConverter.ToInt32(IPAddress.Parse(ipAddress).GetAddressBytes().Reverse().ToArray(), 0);
    }

    public static string IntToIp(int ipInt)
    {
        return new IPAddress(BitConverter.GetBytes(ipInt).Reverse().ToArray()).ToString();
    }

}