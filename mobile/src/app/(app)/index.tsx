import * as DocumentPicker from 'expo-document-picker';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Platform,
  Pressable,
  RefreshControl,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/lib/auth-context';
import { api, UnauthorizedError } from '@/lib/api';
import type { DocumentOut, DocumentStatus } from '@/lib/types';

const ACCEPTED_TYPES = [
  'application/pdf',
  'text/markdown',
  'text/plain',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];

const POLL_INTERVAL_MS = 5000;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusLabel(status: DocumentStatus): string {
  switch (status) {
    case 'uploading':
      return 'Uploading…';
    case 'processing':
      return 'Processing…';
    case 'ready':
      return 'Ready';
    case 'failed':
      return 'Failed';
  }
}

function statusColor(status: DocumentStatus): string {
  switch (status) {
    case 'uploading':
    case 'processing':
      return '#f59e0b'; // amber
    case 'ready':
      return '#22c55e'; // green
    case 'failed':
      return '#ef4444'; // red
  }
}

type DocRowProps = {
  doc: DocumentOut;
  onDelete: (id: string) => void;
  isDeleting: boolean;
};

function DocRow({ doc, onDelete, isDeleting }: DocRowProps) {
  return (
    <ThemedView type="backgroundElement" style={styles.row}>
      <View style={styles.rowContent}>
        <ThemedText type="default" style={styles.filename} numberOfLines={1}>
          {doc.filename}
        </ThemedText>
        <View style={styles.rowMeta}>
          <View style={[styles.statusDot, { backgroundColor: statusColor(doc.status) }]} />
          <ThemedText type="small" themeColor="textSecondary">
            {statusLabel(doc.status)}
          </ThemedText>
          <ThemedText type="small" themeColor="textSecondary" style={styles.metaSep}>
            ·
          </ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {formatBytes(doc.size_bytes)}
          </ThemedText>
        </View>
      </View>
      <Pressable
        onPress={() => onDelete(doc.id)}
        disabled={isDeleting}
        style={({ pressed }) => [styles.deleteButton, pressed && styles.pressed]}
        accessibilityLabel={`Delete ${doc.filename}`}
        accessibilityRole="button">
        {isDeleting ? (
          <ActivityIndicator size="small" />
        ) : (
          <ThemedText type="small" style={styles.deleteText}>
            Delete
          </ThemedText>
        )}
      </Pressable>
    </ThemedView>
  );
}

export default function DocumentsScreen() {
  const { signOut } = useAuth();
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Keep a stable ref to signOut so interval callbacks don't need it as a dep
  const signOutRef = useRef(signOut);
  useEffect(() => {
    signOutRef.current = signOut;
  });

  const loadDocuments = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const docs = await api.listDocuments();
      setDocuments(docs);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        signOutRef.current();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to load documents');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  // Initial load — define async fn inside effect so setState calls happen in a callback
  useEffect(() => {
    let cancelled = false;

    async function initialLoad() {
      setLoading(true);
      setError(null);
      try {
        const docs = await api.listDocuments();
        if (!cancelled) setDocuments(docs);
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          signOutRef.current();
          return;
        }
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load documents');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  // Polling for in-progress documents
  useEffect(() => {
    const hasInProgress = documents.some(
      (d) => d.status === 'uploading' || d.status === 'processing'
    );

    if (hasInProgress) {
      pollRef.current = setInterval(() => {
        loadDocuments(true);
      }, POLL_INTERVAL_MS);
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [documents, loadDocuments]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadDocuments(true);
    setRefreshing(false);
  }, [loadDocuments]);

  const handleUpload = useCallback(async () => {
    let result: DocumentPicker.DocumentPickerResult;
    try {
      result = await DocumentPicker.getDocumentAsync({
        type: ACCEPTED_TYPES,
        copyToCacheDirectory: true,
        multiple: false,
      });
    } catch {
      Alert.alert('Error', 'Could not open document picker');
      return;
    }

    // result.canceled === false means success; result.assets is a non-null array
    if (result.canceled) return;

    const asset = result.assets[0];

    setUploading(true);
    try {
      await api.uploadDocument({
        uri: asset.uri,
        name: asset.name,
        mimeType: asset.mimeType ?? 'application/octet-stream',
      });
      await loadDocuments(true);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        signOutRef.current();
        return;
      }
      Alert.alert('Upload failed', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setUploading(false);
    }
  }, [loadDocuments]);

  const doDelete = useCallback(
    async (id: string) => {
      setDeletingId(id);
      try {
        await api.deleteDocument(id);
        await loadDocuments(true);
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          signOutRef.current();
          return;
        }
        Alert.alert('Delete failed', err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setDeletingId(null);
      }
    },
    [loadDocuments]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      if (Platform.OS !== 'web') {
        Alert.alert('Delete document', 'Are you sure you want to delete this document?', [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Delete',
            style: 'destructive',
            onPress: () => doDelete(id),
          },
        ]);
      } else {
        await doDelete(id);
      }
    },
    [doDelete]
  );

  const renderEmpty = () => {
    if (loading) return null;
    return (
      <ThemedView style={styles.emptyContainer}>
        <ThemedText type="default" themeColor="textSecondary" style={styles.emptyText}>
          No documents yet. Tap Upload to add your first document.
        </ThemedText>
      </ThemedView>
    );
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedView style={styles.header}>
          <ThemedText type="subtitle">Documents</ThemedText>
          <Pressable
            onPress={handleUpload}
            disabled={uploading}
            style={({ pressed }) => [styles.uploadButton, pressed && styles.pressed]}
            accessibilityLabel="Upload document"
            accessibilityRole="button">
            {uploading ? (
              <ActivityIndicator size="small" color="#ffffff" />
            ) : (
              <ThemedText type="smallBold" style={styles.uploadText}>
                Upload
              </ThemedText>
            )}
          </Pressable>
        </ThemedView>

        {error && (
          <ThemedView type="backgroundElement" style={styles.errorBanner}>
            <ThemedText type="small" style={styles.errorText}>
              {error}
            </ThemedText>
            <Pressable onPress={() => loadDocuments()}>
              <ThemedText type="small" style={styles.retryText}>
                Retry
              </ThemedText>
            </Pressable>
          </ThemedView>
        )}

        {loading && documents.length === 0 ? (
          <ThemedView style={styles.loadingContainer}>
            <ActivityIndicator size="large" />
          </ThemedView>
        ) : (
          <FlatList<DocumentOut>
            data={documents}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => (
              <DocRow doc={item} onDelete={handleDelete} isDeleting={deletingId === item.id} />
            )}
            ListEmptyComponent={renderEmpty}
            contentContainerStyle={styles.listContent}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
            }
            ItemSeparatorComponent={() => <View style={styles.separator} />}
          />
        )}
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
  uploadButton: {
    backgroundColor: '#3c87f7',
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.one,
    borderRadius: Spacing.three,
    minWidth: 72,
    alignItems: 'center',
  },
  uploadText: {
    color: '#ffffff',
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
  retryText: {
    color: '#3c87f7',
    marginLeft: Spacing.two,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    flexGrow: 1,
    paddingBottom: Spacing.four,
  },
  separator: {
    height: Spacing.two,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.three,
    borderRadius: Spacing.three,
  },
  rowContent: {
    flex: 1,
    gap: Spacing.one,
  },
  filename: {
    flexShrink: 1,
  },
  rowMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.one,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  metaSep: {
    marginHorizontal: Spacing.half,
  },
  deleteButton: {
    paddingHorizontal: Spacing.two,
    paddingVertical: Spacing.one,
    borderRadius: Spacing.two,
    marginLeft: Spacing.two,
    minWidth: 52,
    alignItems: 'center',
  },
  deleteText: {
    color: '#ef4444',
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
});
