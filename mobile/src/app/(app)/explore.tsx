import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/lib/auth-context';
import { api, UnauthorizedError } from '@/lib/api';
import { useTheme } from '@/hooks/use-theme';
import type { Citation } from '@/lib/types';

type Turn = {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
};

type CitationCardProps = {
  citation: Citation;
};

function CitationCard({ citation }: CitationCardProps) {
  const meta: string[] = [citation.filename];
  if (citation.page !== null) meta.push(`p. ${citation.page}`);
  if (citation.section !== null) meta.push(citation.section);

  return (
    <ThemedView type="backgroundElement" style={styles.citationCard}>
      <ThemedText type="smallBold" numberOfLines={1}>
        [{citation.marker}] {meta.join(' · ')}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary" numberOfLines={3}>
        {citation.snippet}
      </ThemedText>
    </ThemedView>
  );
}

type TurnBubbleProps = {
  turn: Turn;
};

function TurnBubble({ turn }: TurnBubbleProps) {
  const isUser = turn.role === 'user';
  return (
    <View style={[styles.turnContainer, isUser ? styles.turnUser : styles.turnAssistant]}>
      <ThemedView
        type={isUser ? 'backgroundSelected' : 'backgroundElement'}
        style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
        <ThemedText type="default">{turn.content}</ThemedText>
      </ThemedView>
      {!isUser && turn.citations && turn.citations.length > 0 && (
        <View style={styles.citationList}>
          {turn.citations.map((c) => (
            <CitationCard key={c.chunk_id} citation={c} />
          ))}
        </View>
      )}
    </View>
  );
}

export default function ChatScreen() {
  const { signOut } = useAuth();
  const theme = useTheme();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const flatListRef = useRef<FlatList<Turn>>(null);

  // Keep a stable ref to signOut so async callbacks don't capture stale closure
  const signOutRef = useRef(signOut);
  useEffect(() => {
    signOutRef.current = signOut;
  });

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;

    setInput('');
    setError(null);
    setBusy(true);

    const userTurn: Turn = { role: 'user', content: text };
    setTurns((prev) => [...prev, userTurn]);

    try {
      const res = await api.query(text, conversationId);
      const assistantTurn: Turn = {
        role: 'assistant',
        content: res.answer,
        citations: res.citations,
      };
      setConversationId(res.conversation_id);
      setTurns((prev) => [...prev, assistantTurn]);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        signOutRef.current();
        return;
      }
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
      // Remove the optimistically added user turn on error
      setTurns((prev) => prev.slice(0, -1));
    } finally {
      setBusy(false);
    }
  }, [input, busy, conversationId]);

  const handleNewChat = useCallback(() => {
    if (busy) return;
    setConversationId(null);
    setTurns([]);
    setError(null);
    setInput('');
  }, [busy]);

  // Auto-scroll to bottom when turns change
  useEffect(() => {
    if (turns.length > 0) {
      // Use a small delay so layout is complete before scrolling
      const timeout = setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [turns]);

  const renderEmpty = () => (
    <ThemedView style={styles.emptyContainer}>
      <ThemedText type="default" themeColor="textSecondary" style={styles.emptyText}>
        Ask a question about your documents.
      </ThemedText>
    </ThemedView>
  );

  const renderItem = useCallback(({ item }: { item: Turn }) => <TurnBubble turn={item} />, []);

  const keyExtractor = useCallback((_: Turn, index: number) => String(index), []);

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedView style={styles.header}>
          <ThemedText type="subtitle">Chat</ThemedText>
          <Pressable
            onPress={handleNewChat}
            disabled={busy || turns.length === 0}
            style={({ pressed }) => [
              styles.newChatButton,
              (busy || turns.length === 0) && styles.newChatButtonDisabled,
              pressed && styles.pressed,
            ]}
            accessibilityLabel="New chat"
            accessibilityRole="button">
            <ThemedText type="small" themeColor="textSecondary">
              New chat
            </ThemedText>
          </Pressable>
        </ThemedView>

        {error && (
          <ThemedView type="backgroundElement" style={styles.errorBanner}>
            <ThemedText type="small" style={styles.errorText}>
              {error}
            </ThemedText>
            <Pressable onPress={() => setError(null)}>
              <ThemedText type="small" style={styles.dismissText}>
                Dismiss
              </ThemedText>
            </Pressable>
          </ThemedView>
        )}

        <KeyboardAvoidingView
          style={styles.keyboardAvoid}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 24}>
          <FlatList<Turn>
            ref={flatListRef}
            data={turns}
            keyExtractor={keyExtractor}
            renderItem={renderItem}
            ListEmptyComponent={renderEmpty}
            contentContainerStyle={styles.listContent}
            ItemSeparatorComponent={() => <View style={styles.separator} />}
            onContentSizeChange={() => {
              if (turns.length > 0) {
                flatListRef.current?.scrollToEnd({ animated: false });
              }
            }}
          />

          <ThemedView type="backgroundElement" style={styles.inputRow}>
            <TextInput
              style={[styles.textInput, { color: theme.text }]}
              value={input}
              onChangeText={setInput}
              placeholder="Ask a question…"
              placeholderTextColor={theme.textSecondary}
              multiline
              maxLength={4000}
              editable={!busy}
              returnKeyType="send"
              onSubmitEditing={handleSend}
              blurOnSubmit={false}
              accessibilityLabel="Message input"
            />
            <Pressable
              onPress={handleSend}
              disabled={busy || !input.trim()}
              style={({ pressed }) => [
                styles.sendButton,
                (busy || !input.trim()) && styles.sendButtonDisabled,
                pressed && styles.pressed,
              ]}
              accessibilityLabel="Send message"
              accessibilityRole="button">
              {busy ? (
                <ActivityIndicator size="small" color="#ffffff" />
              ) : (
                <ThemedText type="smallBold" style={styles.sendText}>
                  Send
                </ThemedText>
              )}
            </Pressable>
          </ThemedView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'center',
  },
  safeArea: {
    flex: 1,
    maxWidth: MaxContentWidth,
    paddingHorizontal: Spacing.three,
    paddingBottom: BottomTabInset + Spacing.three,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.three,
  },
  newChatButton: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.one,
    borderRadius: Spacing.three,
  },
  newChatButtonDisabled: {
    opacity: 0.4,
  },
  pressed: {
    opacity: 0.7,
  },
  errorBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.two,
    borderRadius: Spacing.two,
    marginBottom: Spacing.two,
  },
  errorText: {
    color: '#ef4444',
    flex: 1,
  },
  dismissText: {
    color: '#3c87f7',
    marginLeft: Spacing.two,
  },
  keyboardAvoid: {
    flex: 1,
  },
  listContent: {
    flexGrow: 1,
    paddingBottom: Spacing.three,
  },
  separator: {
    height: Spacing.three,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.four,
  },
  emptyText: {
    textAlign: 'center',
  },
  turnContainer: {
    width: '100%',
  },
  turnUser: {
    alignItems: 'flex-end',
  },
  turnAssistant: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '85%',
    padding: Spacing.three,
    borderRadius: Spacing.three,
  },
  bubbleUser: {
    borderBottomRightRadius: Spacing.one,
  },
  bubbleAssistant: {
    borderBottomLeftRadius: Spacing.one,
  },
  citationList: {
    marginTop: Spacing.two,
    gap: Spacing.two,
    width: '100%',
  },
  citationCard: {
    padding: Spacing.two,
    borderRadius: Spacing.two,
    gap: Spacing.one,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    borderRadius: Spacing.three,
    padding: Spacing.two,
    marginTop: Spacing.two,
    gap: Spacing.two,
  },
  textInput: {
    flex: 1,
    fontSize: 16,
    lineHeight: 22,
    maxHeight: 120,
    paddingVertical: Spacing.one,
  },
  sendButton: {
    backgroundColor: '#3c87f7',
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Spacing.two,
    minWidth: 60,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
  sendText: {
    color: '#ffffff',
  },
});
