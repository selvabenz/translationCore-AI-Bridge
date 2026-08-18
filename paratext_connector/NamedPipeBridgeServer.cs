using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading;

namespace TranslationCoreAiBridge.ParatextConnector
{
    /// <summary>
    /// Local-only newline-delimited JSON transport. No TCP listener and no Paratext web credentials.
    /// A fresh named-pipe instance is used for each request so the Python client can fail/retry cleanly.
    /// </summary>
    public sealed class NamedPipeBridgeServer : IDisposable
    {
        public const string PipeName = "translationCoreAIBridge";
        private readonly Func<BridgeRequest, BridgeResponse> _handler;
        private volatile bool _stopping;
        private Thread _thread;

        public NamedPipeBridgeServer(Func<BridgeRequest, BridgeResponse> handler)
        {
            if (handler == null) throw new ArgumentNullException("handler");
            _handler = handler;
        }

        public void Start()
        {
            if (_thread != null) return;
            _thread = new Thread(Run);
            _thread.IsBackground = true;
            _thread.Name = "translationCore AI Bridge Paratext pipe";
            _thread.Start();
        }

        private void Run()
        {
            while (!_stopping)
            {
                try
                {
                    using (NamedPipeServerStream pipe = new NamedPipeServerStream(
                        PipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.None))
                    {
                        pipe.WaitForConnection();
                        if (_stopping) return;

                        using (StreamReader reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, true))
                        using (StreamWriter writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true))
                        {
                            writer.AutoFlush = true;
                            string line = reader.ReadLine();
                            if (String.IsNullOrWhiteSpace(line)) continue;

                            BridgeResponse response;
                            BridgeRequest request = null;
                            try
                            {
                                request = BridgeJson.Serializer.Deserialize<BridgeRequest>(line);
                                if (request == null)
                                    throw new InvalidOperationException("Empty connector request.");
                                if (request.protocol != 1)
                                    throw new InvalidOperationException("Unsupported connector protocol version.");
                                response = _handler(request);
                                if (response == null)
                                    response = new BridgeResponse { ok = false, error = "No response from Paratext host adapter." };
                            }
                            catch (Exception ex)
                            {
                                response = new BridgeResponse { ok = false, error = ex.Message };
                            }

                            response.id = request == null ? null : request.id;
                            writer.WriteLine(BridgeJson.Serializer.Serialize(response));
                        }
                    }
                }
                catch (Exception)
                {
                    if (!_stopping) Thread.Sleep(200);
                }
            }
        }

        public void Dispose()
        {
            _stopping = true;
            // Wake WaitForConnection so Paratext can shut down cleanly.
            try
            {
                using (NamedPipeClientStream client = new NamedPipeClientStream(".", PipeName, PipeDirection.Out))
                {
                    client.Connect(100);
                }
            }
            catch { }
            if (_thread != null && _thread.IsAlive)
            {
                try { _thread.Join(800); }
                catch { }
            }
        }
    }
}
