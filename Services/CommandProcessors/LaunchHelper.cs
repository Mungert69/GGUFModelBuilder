using System;
using System.Text;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
using NetworkMonitor.Utils;
using System.Xml.Linq;
using System.IO;
using System.Threading;
using PuppeteerSharp;
using System.Runtime.InteropServices;
using NetworkMonitor.Service.Services.OpenAI;

namespace NetworkMonitor.Processor.Services
{
    public class LaunchHelper
    {

        public static  async Task<LaunchOptions> GetLauncher(NetConnectConfig netConfig, ILogger logger) {
             ViewPortOptions vpo = new ViewPortOptions();
            vpo.Width = 1920;
            vpo.Height = 1280;
              LaunchOptions lo;
                var downloadPath = Path.Combine(netConfig.CommandPath, "chrome-bin");

            // Create the directory if it doesn't exist
            if (!Directory.Exists(downloadPath))
            {
                Directory.CreateDirectory(downloadPath);
            }

            var bfo = new BrowserFetcherOptions
            {
                Path = downloadPath // Set the download path to "chrome-bin"
            };
            logger.LogInformation($"Chromium path is {bfo.Path}");
            var browserFetcher = new BrowserFetcher(bfo);

            // Check if the executable path exists
            string chromiumPath = Path.Combine(bfo.Path, "Chrome");
            if (!Directory.Exists(chromiumPath))
            {
                logger.LogInformation($"Chromium not found. Downloading...");
                await browserFetcher.DownloadAsync();
            }
            else
            {
                logger.LogInformation($"Chromium revision already downloaded.");
            }

            // Dynamically find the Chrome executable based on the platform
            string chromeExecutable = null;
            string osPlatform = "";

            if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux))
            {
                osPlatform = "linux64";
            }
            else if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                osPlatform = "win64";
            }
           
            else
            {
                throw new PlatformNotSupportedException("Unsupported platform");
            }

            // Recursively search for the Chrome executable in the directories
            string FindChromeExecutable(string rootPath, string osPlatform)
            {
                foreach (var dir in Directory.GetDirectories(rootPath, "*", SearchOption.AllDirectories))
                {
                    // Search for the platform-specific subdirectory (e.g., chrome-linux64, win64, etc.)
                    if (dir.Contains(osPlatform))
                    {
                        // Check for the actual executable
                        if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux) )
                        {
                            var executablePath = Path.Combine(dir, "chrome");
                            if (File.Exists(executablePath)) return executablePath;
                        }
                        else if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                        {
                            var executablePath = Path.Combine(dir, "chrome.exe");
                            if (File.Exists(executablePath)) return executablePath;
                        }
                    }
                }
                return null;
            }

            chromeExecutable = FindChromeExecutable(chromiumPath, osPlatform);
            logger.LogInformation($"Using Chrome executable path {chromeExecutable} .");
            if (string.IsNullOrEmpty(chromeExecutable))
            {
                throw new FileNotFoundException($"Chrome executable not found for platform: {osPlatform}.");
            }

            lo = new LaunchOptions()
            {
                Headless = true,
                DefaultViewport = vpo,
                ExecutablePath = chromeExecutable, // Dynamically set the Chrome executable path based on platform
                  Args = new[] { "--no-sandbox", "--disable-setuid-sandbox" } 
            };

        return lo;
        }

       
    }



}