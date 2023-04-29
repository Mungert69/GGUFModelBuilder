using NetworkMonitor.Objects;
using NetworkMonitor.Connection;
using System.Net;
using System.Threading.Tasks;
using Xunit;
namespace NetworkMonitor.Tests.Connection
{
    public class DNSConnectTests
    {
        private PingParams pingParams;
        public DNSConnectTests()
        {
            pingParams = new PingParams();

            pingParams.Timeout=10000;
        }
        [Fact]
        public async Task Test_DNSConnect_Success()
        {
            // Arrange
            MonitorPingInfo pingInfo = new MonitorPingInfo
            {
                Address = "www.google.com",
                Timeout = 5000,
                EndPointType="DNS"
            };
            pingInfo.Address="www.google.com";
            DNSConnect dnsConnect = new DNSConnect();
            dnsConnect.PingParams=pingParams;
            dnsConnect.MonitorPingInfo=pingInfo;

            // Act
            await dnsConnect.Connect();
            // Assert
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.Contains("Found :", pingInfo.Status);
            Assert.NotEmpty(pingInfo.PingInfos);
            Assert.Equal("Success", pingInfo.PingInfos[0].Status);
            Assert.NotEqual<ushort?>(0, pingInfo.PingInfos[0].RoundTripTime);
        }
        [Fact]
        public async Task Test_DNSConnect_Timeout()
        {
            // Arrange
            MonitorPingInfo pingInfo = new MonitorPingInfo
            {
                Address = "www.google.com",
                Timeout = 1,
                EndPointType="DNS"
            };
            DNSConnect dnsConnect = new DNSConnect();
              dnsConnect.PingParams=pingParams;
            dnsConnect.MonitorPingInfo=pingInfo;
            // Act
            await dnsConnect.Connect();
            // Assert
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.Contains("Timeout", pingInfo.Status);
            Assert.NotEmpty(pingInfo.PingInfos);
            Assert.Equal("Timeout", pingInfo.PingInfos[0].Status);
        }
        [Fact]
        public async Task Test_DNSConnect_No_IP_Addresses_Found()
        {
            // Arrange
            MonitorPingInfo pingInfo = new MonitorPingInfo
            {
                Address = "www.invalid-domain.com",
                Timeout = 5000,
                EndPointType="DNS"
            };
            DNSConnect dnsConnect = new DNSConnect();
              dnsConnect.PingParams=pingParams;
            dnsConnect.MonitorPingInfo=pingInfo;
            // Act
            await dnsConnect.Connect();
            // Assert
            Assert.Equal(1, pingInfo.PacketsSent);
            Assert.Contains("DNS:Failed to connect", pingInfo.Status);
            Assert.NotEmpty(pingInfo.PingInfos);
            Assert.Contains("Name or service not known", pingInfo.PingInfos[0].Status);
        }
    }
}
