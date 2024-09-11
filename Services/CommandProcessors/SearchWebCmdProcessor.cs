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
using NetworkMonitor.Service.Services.OpenAI;

namespace NetworkMonitor.Processor.Services
{
    public class SearchWebCmdProcessor : CmdProcessor
    {

        public SearchWebCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
: base(logger, cmdProcessorStates, rabbitRepo, netConfig)
        {

        }
        public override async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            var result = new ResultObj();
            string output = "";
            try
            {
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdDisplayName} is not enabled or installed on this agent.");
                    output = $"{_cmdProcessorStates.CmdDisplayName} is not available on this agent. Try installing the Quantum Secure Agent or select an agent that has Openssl enabled.\n";
                    result.Message = await SendMessage(output, processorScanDataObj);
                    result.Success = false;
                    return result;

                }

                output = await FetchUrls(arguments);
                cancellationToken.ThrowIfCancellationRequested();
                result.Success = true;


            }
            catch (Exception e)
            {
                _logger.LogError($"Error : running {_cmdProcessorStates.CmdName} command. Errro was : {e.Message}");
                output += $"Error : running {_cmdProcessorStates.CmdName} command. Error was : {e.Message}\n";
                result.Success = false;
            }
            result.Message = output;
            return result;
        }
        static async Task RandomDelay(int min, int max)
        {
            var random = new Random();
            int delay = random.Next(min, max);
            await Task.Delay(delay);
        }

        // Function to fetch URLs from Google Search
        private async Task<string> FetchUrls(string searchTerm)
        {
            string jsonResult = "No results found";
            ViewPortOptions vpo = new ViewPortOptions();
            vpo.Width = 1920;
            vpo.Height = 1280;
            // Define the path where Chromium will be downloaded (create "chrome-bin" folder in the current directory)
            var downloadPath = Path.Combine(_netConfig.CommandPath, "chrome-bin");

            // Create the directory if it doesn't exist
            if (!Directory.Exists(downloadPath))
            {
                Directory.CreateDirectory(downloadPath);
            }

            var bfo = new BrowserFetcherOptions
            {
                Path = downloadPath // Set the download path to "chrome-bin"
            };
            _logger.LogInformation($"Chromium path is {bfo.Path}");
            var browserFetcher = new BrowserFetcher(bfo);

            // Check if the executable path exists
            string chromiumPath = Path.Combine(bfo.Path, "Chrome"); // Path to Chrome on Windows
            if (!Directory.Exists(chromiumPath))
            {
                _logger.LogInformation($"Chromium not found. Downloading...");
                await browserFetcher.DownloadAsync();
            }
            else
            {
                _logger.LogInformation($"Chromium revision already downloaded.");
            }
            var lo = new LaunchOptions()
            {
                Headless = true,
                DefaultViewport = vpo,

            };

            using (var browser = await Puppeteer.LaunchAsync(lo))
            {
                var page = await browser.NewPageAsync();
                _logger.LogInformation($"Navigating to Google Search with term: {searchTerm}");

                await RandomDelay(1500, 3000); // Random delay between 1.5s and 3s
                await page.GoToAsync($"https://www.google.com/search?q={Uri.EscapeDataString(searchTerm)}");

                _logger.LogInformation("Waiting for search results to load...");
                await RandomDelay(1500, 3000); // Random delay between 1.5s and 3s

                // Wait for the search results container to be visible
                await page.WaitForSelectorAsync("#search", new WaitForSelectorOptions { Timeout = 30000 });
                _logger.LogInformation("Search results loaded.");

                await RandomDelay(1500, 3000); // Random delay between 1.5s and 3s

                // Output the HTML content for debugging
                var content = await page.GetContentAsync();
                _logger.LogInformation("Page content:", content.Substring(0, Math.Min(5000, content.Length))); // Print the first 5000 characters

                await RandomDelay(1500, 3000); // Random delay between 1.5s and 3s

                // Extract URLs from search results
                var urls = await page.EvaluateFunctionAsync<string[]>(
                    "() => Array.from(document.querySelectorAll('.g a')).map(link => link.href).filter(href => href.includes('http') && !href.includes('webcache'))"
                );

                _logger.LogInformation("URLs extracted: " + string.Join(", ", urls));

                await browser.CloseAsync();
                _logger.LogInformation("Browser closed.");
                var jsonBuilder = new StringBuilder();
                jsonBuilder.Append("[");
                for (int i = 0; i < urls.Length; i++)
                {
                    jsonBuilder.Append($"\"{urls[i]}\"");
                    if (i < urls.Length - 1) jsonBuilder.Append(", ");
                }
                jsonBuilder.Append("]");

                jsonResult = jsonBuilder.ToString();
                
            }
            return jsonResult;
        }


    }



}