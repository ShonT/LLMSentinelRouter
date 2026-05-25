package main

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ShonT/LLMSentinelRouter/internal/config"
	"github.com/ShonT/LLMSentinelRouter/internal/metrics"
	"github.com/ShonT/LLMSentinelRouter/internal/server"
	"github.com/ShonT/LLMSentinelRouter/internal/storage"
)

func main() {
	settings := config.LoadSettings()
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		if err := healthcheck(settings); err != nil {
			log.Fatal(err)
		}
		return
	}
	ctx := context.Background()
	manager, err := config.NewManager(settings)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}
	store, err := storage.Open(ctx, settings.DatabaseURL)
	if err != nil {
		log.Fatalf("open storage: %v", err)
	}
	defer store.Close()
	collector := metrics.NewCollector("./data/metrics/metrics.jsonl")
	stopWatch := make(chan struct{})
	go manager.Watch(stopWatch, time.Second)
	app := server.New(settings, manager, store, collector)
	httpServer := &http.Server{
		Addr:              settings.Host + ":" + settings.Port,
		Handler:           app.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	errCh := make(chan error, 1)
	go func() {
		log.Printf("SentinelRouter listening on %s", httpServer.Addr)
		errCh <- httpServer.ListenAndServe()
	}()
	var dashboardServer *http.Server
	if settings.DashboardPort != "" && settings.DashboardPort != settings.Port {
		dashboardServer = &http.Server{
			Addr:              settings.Host + ":" + settings.DashboardPort,
			Handler:           app.Handler(),
			ReadHeaderTimeout: 10 * time.Second,
		}
		go func() {
			log.Printf("SentinelRouter dashboard listening on %s", dashboardServer.Addr)
			if err := dashboardServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
				log.Printf("dashboard server error: %v", err)
			}
		}()
	}
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	select {
	case sig := <-sigCh:
		log.Printf("received signal %s", sig)
	case err := <-errCh:
		if err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}
	close(stopWatch)
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		log.Printf("shutdown error: %v", err)
	}
	if dashboardServer != nil {
		if err := dashboardServer.Shutdown(shutdownCtx); err != nil {
			log.Printf("dashboard shutdown error: %v", err)
		}
	}
}

func healthcheck(settings config.Settings) error {
	url := fmt.Sprintf("http://127.0.0.1:%s/health", settings.Port)
	client := http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("healthcheck status %d", resp.StatusCode)
	}
	return nil
}
