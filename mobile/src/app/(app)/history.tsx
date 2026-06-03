import { router } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/lib/auth-context';
import { api, UnauthorizedError } from '@/lib/api';
import type { ConversationOut } from '@/lib/types';

function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function HistoryScreen() {
  const { signOut } = useAuth();
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signOutRef = useRef(signOut);
  useEffect(() => {
    signOutRef.current = signOut;
  });

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      setConversations(await api.listConversations());
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        signOutRef.current();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function initialLoad() {
      setLoading(true);
      setError(null);
      try {
        const convos = await api.listConversations();
        if (!cancelled) setConversations(convos);
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          signOutRef.current();
          return;
        }
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load conversations');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  }, [load]);

  const openConversation = useCallback((id: string) => {
    router.navigate({ pathname: '/explore', params: { c: id } });
  }, []);

  const renderEmpty = () => {
    if (loading) return null;
    return (
      <ThemedView style={styles.emptyContainer}>
        <ThemedText type="default" themeColor="textSecondary" style={styles.emptyText}>
          No conversations yet. Start one in the Chat tab.
        </ThemedText>
      </ThemedView>
    );
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedView style={styles.header}>
          <ThemedText type="subtitle">History</ThemedText>
        </ThemedView>

        {error && (
          <ThemedView type="backgroundElement" style={styles.errorBanner}>
            <ThemedText type="small" style={styles.errorText}>
              {error}
            </ThemedText>
            <Pressable onPress={() => load()}>
              <ThemedText type="small" style={styles.retryText}>
                Retry
              </ThemedText>
            </Pressable>
          </ThemedView>
        )}

        {loading && conversations.length === 0 ? (
          <ThemedView style={styles.loadingContainer}>
            <ActivityIndicator size="large" />
          </ThemedView>
        ) : (
          <FlatList<ConversationOut>
            data={conversations}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => (
              <Pressable
                onPress={() => openConversation(item.id)}
                style={({ pressed }) => pressed && styles.pressed}
                accessibilityRole="button"
                accessibilityLabel={`Open conversation: ${item.preview}`}>
                <ThemedView type="backgroundElement" style={styles.row}>
                  <ThemedText type="default" numberOfLines={1}>
                    {item.preview || 'Untitled'}
                  </ThemedText>
                  <ThemedText type="small" themeColor="textSecondary">
                    {formatRelative(item.last_message_at)}
                  </ThemedText>
                </ThemedView>
              </Pressable>
            )}
            ListEmptyComponent={renderEmpty}
            contentContainerStyle={styles.listContent}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
            ItemSeparatorComponent={() => <View style={styles.separator} />}
          />
        )}
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, flexDirection: 'row', justifyContent: 'center' },
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
  pressed: { opacity: 0.7 },
  errorBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.two,
    borderRadius: Spacing.two,
    marginBottom: Spacing.two,
  },
  errorText: { color: '#ef4444', flex: 1 },
  retryText: { color: '#3c87f7', marginLeft: Spacing.two },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  listContent: { flexGrow: 1, paddingBottom: Spacing.four },
  separator: { height: Spacing.two },
  row: { padding: Spacing.three, borderRadius: Spacing.three, gap: Spacing.one },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.four,
  },
  emptyText: { textAlign: 'center' },
});
