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
    public class CrawlPageCmdProcessor : CmdProcessor
    {

        public CrawlPageCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
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

                output = await ExtractContent(arguments);
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
        private async Task RandomDelay(int min, int max)
        {
            var random = new Random();
            int delay = random.Next(min, max);
            await Task.Delay(delay);
        }

        private async Task<string> ExtractContent(string url)
        {
            _logger.LogInformation("Starting browser...");

            // Set browser options
           ViewPortOptions vpo = new ViewPortOptions();
            vpo.Width = 1920;
            vpo.Height = 1280;
            // Define the path where Chromium will be downloaded (create "chrome-bin" folder in the current directory)
            var downloadPath = Path.Combine(Directory.GetCurrentDirectory(), "chrome-bin");

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
            

            // Launch browser
            using (var browser = await Puppeteer.LaunchAsync(lo))
            {
                var page = await browser.NewPageAsync();

                _logger.LogInformation($"Navigating to {url}");
                await page.GoToAsync(url);

                // Wait for a random delay to mimic human browsing
                await RandomDelay(2000, 5000);

                _logger.LogInformation("Waiting for page content to load...");
                await page.WaitForSelectorAsync("body");

                // Extract text content with inline links, excluding script and style tags
                var content = await page.EvaluateFunctionAsync<string>(@"() => {
                // Function to recursively get text from nodes
                const getTextWithLinks = (node) => {
                    let text = '';
                    if (node.nodeType === Node.TEXT_NODE) {
                        return node.textContent;
                    } else if (node.nodeType === Node.ELEMENT_NODE) {
                        if (node.nodeName === 'SCRIPT' || node.nodeName === 'STYLE') {
                            return '';
                        }
                        if (node.nodeName === 'A') {
                            return `[${node.textContent}](${node.href})`;
                        }
                        // Process child nodes
                        for (let child of node.childNodes) {
                            text += getTextWithLinks(child);
                        }
                    }
                    return text;
                };

                // Start from the body element
                return getTextWithLinks(document.body)
                    .replace(/\s\s+/g, ' ')  // Remove excessive whitespace
                    .trim();
            }");

                _logger.LogInformation("Page content extracted.");
                return content;
            }
        }

    }



}