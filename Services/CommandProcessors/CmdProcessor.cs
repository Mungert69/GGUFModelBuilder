using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
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
using System.Text.Json;

namespace NetworkMonitor.Processor.Services
{
    public interface ICmdProcessor : IDisposable
    {
        Task Scan();
        Task CancelScan();
        Task<ResultObj> QueueCommand(CancellationTokenSource cancellationToken, ProcessorScanDataObj processorScanDataObj);
        Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null);
        Task CancelRun();
        bool UseDefaultEndpoint { get; set; }
    }
    public abstract class CmdProcessor : ICmdProcessor
    {
        protected readonly ILogger _logger;
        protected readonly ILocalCmdProcessorStates _cmdProcessorStates;
        protected readonly IRabbitRepo _rabbitRepo;
        protected readonly NetConnectConfig _netConfig;
        protected CancellationTokenSource _cancellationTokenSource;
        private readonly ConcurrentQueue<CommandTask> _currentQueue;
        private readonly SemaphoreSlim _semaphore;
        public bool UseDefaultEndpoint { get => _cmdProcessorStates.UseDefaultEndpointType; set => _cmdProcessorStates.UseDefaultEndpointType = value; }
        public CmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
        {
            _logger = logger;
            _cmdProcessorStates = cmdProcessorStates;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;
            _cmdProcessorStates.OnStartScanAsync += Scan;
            _cmdProcessorStates.OnCancelScanAsync += CancelScan;
            _cmdProcessorStates.OnAddServicesAsync += AddServices;
            _currentQueue = new ConcurrentQueue<CommandTask>();
            _semaphore = new SemaphoreSlim(5);
            _ = StartQueueProcessorAsync();

        }

        private async Task StartQueueProcessorAsync()
        {
            while (true) // Keep processing tasks indefinitely
            {
                await ProcessQueueAsync();
                await Task.Delay(1000);
            }
        }


        public virtual void Dispose()
        {
            _cmdProcessorStates.OnStartScanAsync -= Scan;
            _cmdProcessorStates.OnCancelScanAsync -= CancelScan;
            _cmdProcessorStates.OnAddServicesAsync -= AddServices;
            _cancellationTokenSource?.Dispose();
        }

        public virtual async Task Scan()
        {

            _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdName} Scan Command is not enabled or installed on this agent.");
            var output = $"The {_cmdProcessorStates.CmdDisplayName}  Scan Command is not available on this agent. Try using another agent.\n";
            _cmdProcessorStates.IsSuccess = false;
            _cmdProcessorStates.IsRunning = false;
            await SendMessage(output, null);



        }

        public virtual async Task AddServices()
        {
            _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdName} Add Services command is not enabled or installed on this agent.");
            var output = $"{_cmdProcessorStates.CmdDisplayName} Add Services command is not available on this agent. Try using another agent.\n";
            _cmdProcessorStates.IsSuccess = false;
            _cmdProcessorStates.IsRunning = false;
            await SendMessage(output, null);
        }

        public virtual async Task CancelScan()
        {
            if (!_cmdProcessorStates.IsCmdAvailable)
            {
                _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdName} command is not enabled or installed on this agent.");
                var output = $"The {_cmdProcessorStates.CmdDisplayName} command is not available on this agent. Try using another agent.\n";
                _cmdProcessorStates.IsSuccess = false;
                _cmdProcessorStates.IsRunning = false;
                await SendMessage(output, null);
                return;

            }
            if (_cmdProcessorStates.IsRunning && _cancellationTokenSource != null)
            {
                _logger.LogWarning($" Warning : Cancelling the ongoing {_cmdProcessorStates.CmdName} scan.");
                _cmdProcessorStates.RunningMessage += $"Cancelling the ongoing {_cmdProcessorStates.CmdDisplayName} scan...\n";
                if (_cancellationTokenSource != null) _cancellationTokenSource.Cancel();
            }
            else
            {
                _logger.LogInformation($"No {_cmdProcessorStates.CmdName} scan is currently running.");
                _cmdProcessorStates.CompletedMessage += $"No {_cmdProcessorStates.CmdDisplayName} scan is currently running.\n";
            }
        }


        public async Task<ResultObj> QueueCommand(CancellationTokenSource cts, ProcessorScanDataObj processorScanDataObj)
        {
            var tcs = new TaskCompletionSource<ResultObj>();
            var commandTask = new CommandTask(
                processorScanDataObj.MessageID,
                async () =>
                {
                    try
                    {
                        // Run the command and set the result in the TaskCompletionSource
                        var result = await RunCommand(processorScanDataObj.Arguments, cts.Token, processorScanDataObj);
                        tcs.SetResult(result);
                    }
                    catch (Exception ex)
                    {
                        tcs.SetException(ex); // If an error occurs, propagate it to the caller
                    }
                },
                cts
            );

            _currentQueue.Enqueue(commandTask);
            ResultObj taskResult = await tcs.Task;
            taskResult.Message = await SendMessage(taskResult.Message, processorScanDataObj);
            return taskResult;
            // return await tcs.Task; // Return the Task<string> that will complete once the command finishes
        }


        private async Task ProcessQueueAsync()
        {
            if (_currentQueue.TryDequeue(out var commandTask))
            {
                if (!commandTask.IsRunning)
                {
                    await _semaphore.WaitAsync(); // Wait for a semaphore slot to be available

                    commandTask.IsRunning = true; // Mark the task as running

                    var task = Task.Run(async () =>
                    {
                        try
                        {
                            await commandTask.TaskFunc(); // Await the task execution
                            commandTask.IsSuccessful = true; // Mark the task as successful
                        }
                        catch (OperationCanceledException)
                        {
                            _logger.LogInformation($"Command {commandTask.MessageId} was cancelled.");
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError($"Command {commandTask.MessageId} failed with exception: {ex.Message}");
                        }
                        finally
                        {
                            commandTask.IsRunning = false; // Mark the task as not running
                            _semaphore.Release(); // Release the semaphore slot
                        }
                    });

                    // Await the task to handle completion and errors
                    await task;
                }
            }
            else
            {
                // No tasks available, briefly delay to prevent tight loop
                await Task.Delay(1000);
            }
        }


        public async Task CancelCommand(string messageId)
        {
            var taskToCancel = _currentQueue.FirstOrDefault(t => t.MessageId == messageId);

            if (taskToCancel != null)
            {
                taskToCancel.CancellationTokenSource.Cancel();
                await taskToCancel.TaskFunc(); // Wait for the task to complete
            }
            else
            {
                _logger.LogWarning($"No running command found with MessageID: {messageId}");
            }
        }


        public virtual async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
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


                using (var process = new Process())
                {
                    process.StartInfo.FileName = _netConfig.CommandPath + _cmdProcessorStates.CmdName;
                    process.StartInfo.Arguments = arguments;
                    process.StartInfo.UseShellExecute = false;
                    process.StartInfo.RedirectStandardOutput = true;
                    process.StartInfo.RedirectStandardError = true; // Add this to capture standard error

                    process.StartInfo.CreateNoWindow = true;
                    process.StartInfo.WorkingDirectory = _netConfig.CommandPath;

                    // Start the process
                    process.Start();

                    // Register a callback to kill the process if cancellation is requested
                    using (cancellationToken.Register(() =>
                    {
                        if (!process.HasExited)
                        {
                            _logger.LogInformation($"Cancellation requested, killing the {_cmdProcessorStates.CmdDisplayName} process...");
                            process.Kill();
                        }
                    }))
                    {
                        // Read the output asynchronously, supporting cancellation
                        output = await process.StandardOutput.ReadToEndAsync().ConfigureAwait(false);
                        //output += " "+await process.StandardError.ReadToEndAsync().ConfigureAwait(false);
                        // Capture standard error
                        string errorOutput = await process.StandardError.ReadToEndAsync().ConfigureAwait(false);

                        if (!string.IsNullOrWhiteSpace(errorOutput) && processorScanDataObj != null)
                        {
                            output = "Error: " + errorOutput + "\n" + output; // Append the error to the output
                        }
                        // Wait for the process to exit
                        await process.WaitForExitAsync().ConfigureAwait(false);

                        // Throw if cancellation was requested after the process started
                        cancellationToken.ThrowIfCancellationRequested();
                        result.Success = true;
                    }
                }
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


        public virtual async Task CancelRun()
        {
            if (_cmdProcessorStates.IsCmdRunning && _cancellationTokenSource != null)
            {
                _logger.LogInformation($"Cancelling the ongoing {_cmdProcessorStates.CmdName} execution.");
                _cmdProcessorStates.RunningMessage += $"Cancelling the ongoing {_cmdProcessorStates.CmdDisplayName} execution...\n";
                _cancellationTokenSource.Cancel();
            }
            else
            {
                _logger.LogInformation($"No {_cmdProcessorStates.CmdName} execution is currently running.");
                _cmdProcessorStates.CompletedMessage += $"No {_cmdProcessorStates.CmdName} execution is currently running.\n";
            }
        }
        protected virtual async Task<string> SendMessage(string output, ProcessorScanDataObj? processorScanDataObj)
        {
            if (processorScanDataObj == null) return output;
            else
            {
                try
                {
                    if (processorScanDataObj.LineLimit == -1)
                    {
                        // Default to appsetting.json CmdReturnDataLineLimit
                        processorScanDataObj.LineLimit = _netConfig.CmdReturnDataLineLimit;
                    }

                    var lines = output.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);

                    int totalLines = lines.Length;
                    int totalPages = (int)Math.Ceiling((double)totalLines / processorScanDataObj.LineLimit);

                    // Ensure Page number is within valid range
                    if (processorScanDataObj.Page < 1)
                    {
                        processorScanDataObj.Page = 1;
                    }
                    else if (processorScanDataObj.Page > totalPages)
                    {
                        processorScanDataObj.Page = totalPages;
                        output = $"[Warning: Page {processorScanDataObj.Page} is beyond the total number of pages ({totalPages}). Showing the last available page ({totalPages}).]";

                    }

                    // Calculate the starting index based on the Page number
                    int startLineIndex = (processorScanDataObj.Page - 1) * processorScanDataObj.LineLimit;
                    int endLineIndex = Math.Min(startLineIndex + processorScanDataObj.LineLimit, totalLines);

                    // Get the lines for the current page
                    var paginatedLines = lines.Skip(startLineIndex).Take(endLineIndex - startLineIndex);

                    output = string.Join(" \n ", paginatedLines);

                    // Add a footer with pagination information
                    output += " \n " + $" [Showing page {processorScanDataObj.Page} of {totalPages}. Total lines: {totalLines}.]";

                    if (processorScanDataObj.Page < totalPages)
                    {
                        output += " \n " + $" [Output truncated to {processorScanDataObj.LineLimit} lines per page. There is more data on other pages. If you want to see more data choose another page of data to view. If there is a large amount of data to view consider refining the query to return less data.]";
                    }
                    var options = new JsonSerializerOptions
                    {
                        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
                    };

                    string jsonString = JsonSerializer.Serialize(output, options);
                    //string jsonString = JsonSerializer.Serialize(output);
                    if (jsonString.StartsWith("\""))
                    {
                        jsonString = jsonString.Substring(1);
                    }

                    // Remove trailing double quote if present
                    if (jsonString.EndsWith("\""))
                    {
                        jsonString = jsonString.Substring(0, jsonString.Length - 1);
                    }
                    processorScanDataObj.ScanCommandOutput = jsonString;
                    await _rabbitRepo.PublishAsync<ProcessorScanDataObj>(processorScanDataObj.CallingService, processorScanDataObj);
                    _logger.LogInformation($" Success : sending with MessageID {processorScanDataObj.MessageID} output : {processorScanDataObj.ScanCommandOutput}");
                }

                catch (Exception e)
                {
                    output += $" Error : during publish {_cmdProcessorStates.CmdName} command output: {e.Message}";
                    _logger.LogError(output);

                }
                return output;


            }
        }

    }





}