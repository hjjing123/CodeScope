import { useState, useEffect, useCallback, useRef } from 'react';
import type { Job, JobListParams } from '../types/scan';
import { ScanService } from '../services/scan';
import { message } from 'antd';

const TERMINAL_JOB_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELED', 'TIMEOUT']);

export const useJobs = (initialParams: JobListParams = {}) => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [params, setParams] = useState<JobListParams>(initialParams);
  const pollingRef = useRef<number | null>(null);

  const fetchJobs = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await ScanService.listJobs(params);
      setJobs(res.items);
      setTotal(res.total);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
      if (!silent) message.error('Failed to fetch jobs');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [params]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Polling logic
  useEffect(() => {
    // Stop existing polling
    if (pollingRef.current) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    // Check if there are any running jobs
    // We consider jobs that are NOT in a final state as running
    const hasRunningJobs = jobs.some((job) => !TERMINAL_JOB_STATUSES.has(job.status));

    if (hasRunningJobs) {
      pollingRef.current = window.setInterval(() => {
        fetchJobs(true);
      }, 5000);
    }

    return () => {
      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
      }
    };
  }, [jobs, fetchJobs]);

  const updateParams = useCallback((newParams: Partial<JobListParams>) => {
    setParams(prev => ({ ...prev, ...newParams }));
  }, []);

  return {
    jobs,
    loading,
    total,
    params,
    setParams: updateParams,
    refresh: () => fetchJobs(false),
  };
};
