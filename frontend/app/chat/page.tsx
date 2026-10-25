"use client";

import { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";

interface Msg {
  role: "user" | "assistant";
  content: string;
}

interface ChatResponse {
  choices: { message: { role: string; content: string } }[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setInput("");
    setSending(true);
    try {
      const data = await api.post<ChatResponse>("/admin/generate/chat", {
        messages: next,
        stream: false,
      });
      const reply = data.choices?.[0]?.message?.content ?? "(không có phản hồi)";
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gửi tin nhắn thất bại");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Chat Muse</h1>
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 min-h-0">
        {messages.length === 0 && <p className="text-muted-foreground text-sm">Chưa có tin nhắn nào.</p>}
        {messages.map((m, i) => (
          <div key={i} className={`rounded px-3 py-2 text-sm max-w-[80%] whitespace-pre-wrap ${
            m.role === "user" ? "bg-primary text-primary-foreground ml-auto" : "bg-accent"
          }`}>
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="flex gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Nhắn tin... (Enter để gửi, Shift+Enter xuống dòng)"
          rows={2}
          className="flex-1"
        />
        <Button onClick={send} disabled={sending || !input.trim()}>
          {sending ? "Đang gửi..." : "Gửi"}
        </Button>
      </div>
    </div>
  );
}
