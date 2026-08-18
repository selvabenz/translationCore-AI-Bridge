using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;

namespace TranslationCoreAiBridge.ParatextConnector
{
    public sealed class BridgeRequest
    {
        public int protocol { get; set; }
        public string id { get; set; }
        public string action { get; set; }
        public Dictionary<string, object> payload { get; set; }
    }

    public sealed class BridgeResponse
    {
        public BridgeResponse()
        {
            protocol = 1;
            capabilities = new string[0];
        }

        public int protocol { get; set; }
        public string id { get; set; }
        public bool ok { get; set; }
        public string error { get; set; }
        public string message { get; set; }

        public string user { get; set; }
        public string project_name { get; set; }
        public string project_id { get; set; }
        public string project_language { get; set; }
        public string reference { get; set; }
        public string selected_text { get; set; }
        public string selection_reference { get; set; }
        public string before_context { get; set; }
        public string after_context { get; set; }
        public int selection_offset { get; set; }
        public string sync_group { get; set; }
        public string paratext_version { get; set; }
        public string plugin_version { get; set; }
        public long state_revision { get; set; }
        public string last_event { get; set; }
        public string last_origin_id { get; set; }
        public bool note_created { get; set; }
        public string[] capabilities { get; set; }
    }

    internal static class BridgeJson
    {
        internal static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();

        internal static string GetString(IDictionary<string, object> payload, string key)
        {
            if (payload == null || !payload.ContainsKey(key) || payload[key] == null)
                return String.Empty;
            return Convert.ToString(payload[key]) ?? String.Empty;
        }
    }
}
