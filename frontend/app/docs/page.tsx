"use client";

import { useEffect, useState } from "react";
import { api, hasRole } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre className="bg-muted rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap">
      <code>{children}</code>
    </pre>
  );
}

export default function DocsPage() {
  const { me } = useAuth();
  const [apiKey, setApiKey] = useState<string | null>(null);
  const base = api.base || (typeof window !== "undefined" ? window.location.origin : "");

  useEffect(() => {
    if (hasRole(me, "owner")) {
      api.get<{ api_key: string }>("/admin/apikey").then((d) => setApiKey(d.api_key)).catch(() => {});
    }
  }, [me]);

  const key = apiKey ?? "<API_KEY>";

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-xl font-semibold">Hướng dẫn API</h1>

      <section className="space-y-2">
        <h2 className="font-medium">Model</h2>
        <p className="text-sm text-muted-foreground">
          <code>muse-spark</code> (chat/code), <code>muse-image</code> (ảnh), <code>muse-video</code> (video).
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Địa chỉ API</h2>
        <Code>{base}/v1</Code>
        {!hasRole(me, "owner") && (
          <p className="text-xs text-muted-foreground">API key chỉ owner xem được — hỏi owner lấy key cho ứng dụng của bạn.</p>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Chat</h2>
        <Code>{`curl ${base}/v1/chat/completions \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"muse-spark","messages":[{"role":"user","content":"Xin chào"}]}'`}</Code>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Tạo ảnh</h2>
        <Code>{`curl ${base}/v1/images/generations \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"muse-image","prompt":"a cat in space","size":"16:9"}'`}</Code>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Tạo video</h2>
        <Code>{`curl ${base}/v1/videos \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"muse-video","prompt":"a dog running on the beach","duration":10,"size":"16:9"}'

# Poll tiến độ:
curl ${base}/v1/videos/{task_id} -H "Authorization: Bearer ${key}"`}</Code>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Python (OpenAI SDK)</h2>
        <Code>{`from openai import OpenAI
client = OpenAI(base_url="${base}/v1", api_key="${key}")
resp = client.chat.completions.create(model="muse-spark", messages=[{"role": "user", "content": "Xin chào"}])
print(resp.choices[0].message.content)`}</Code>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Lưu ý</h2>
        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
          <li>Bearer key (API key) dành cho ứng dụng/script bên ngoài gọi API lập trình.</li>
          <li>Tài khoản đăng nhập web (bạn đang dùng) tự động dùng được tất cả tính năng qua giao diện, không cần key.</li>
          <li>tool_calls/function_calling chưa được Muse hỗ trợ.</li>
        </ul>
      </section>
    </div>
  );
}
